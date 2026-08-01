"""Rutas HTTP para extraer CFDI y descargar reportes Excel."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse

from app.services.cfdi.extractor import MAX_XML_BYTES, generar_excel_desde_xmls
from app.services.cfdi.jobs import crear_job, eliminar_job, obtener_job


router = APIRouter(prefix="/cfdi", tags=["CFDI"])
MAX_ARCHIVOS_POR_SOLICITUD = 50
TAMANIO_BLOQUE = 1024 * 1024


@router.get("/jobs/{job_id}/download", summary="Descarga reporte CFDI de un job")
def descargar_reporte_cfdi(
    job_id: str,
    background_tasks: BackgroundTasks,
) -> FileResponse:
    """Entrega reporte generado sin aceptar rutas enviadas por el cliente."""
    job = obtener_job(job_id)
    if job is None or not job.ruta_salida.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Reporte CFDI no encontrado",
        )

    background_tasks.add_task(eliminar_job, job_id)
    return FileResponse(
        path=job.ruta_salida,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename="reporte_cfdi.xlsx",
        background=background_tasks,
    )


async def _guardar_xml(archivo: UploadFile, destino: Path) -> None:
    """Guarda carga por bloques y limita tamaño antes de procesarla."""
    total = 0
    with destino.open("wb") as salida:
        while bloque := await archivo.read(TAMANIO_BLOQUE):
            total += len(bloque)
            if total > MAX_XML_BYTES:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=f"{archivo.filename}: supera límite de 20 MB",
                )
            salida.write(bloque)
    await archivo.close()


@router.post("/upload", summary="Carga XML CFDI para el asistente")
async def cargar_xml_para_asistente(
    archivos: list[UploadFile] = File(..., description="Uno o mÃ¡s archivos XML CFDI 4.0"),
) -> dict[str, object]:
    """Guarda XML y devuelve un identificador para usarlo desde el chat."""
    if not archivos:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="EnvÃ­a al menos un XML")
    if len(archivos) > MAX_ARCHIVOS_POR_SOLICITUD:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"MÃ¡ximo {MAX_ARCHIVOS_POR_SOLICITUD} XMLs por solicitud",
        )

    directorio_temporal = Path(tempfile.mkdtemp(prefix="flucito_cfdi_job_"))
    rutas_xml: list[Path] = []
    nombres: list[str] = []
    try:
        for indice, archivo in enumerate(archivos, start=1):
            nombre = Path(archivo.filename or f"archivo_{indice}.xml").name
            if Path(nombre).suffix.lower() != ".xml":
                await archivo.close()
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"{nombre}: solo se aceptan archivos .xml",
                )

            destino = directorio_temporal / f"{indice}_{nombre}"
            await _guardar_xml(archivo, destino)
            rutas_xml.append(destino)
            nombres.append(nombre)
    except HTTPException:
        shutil.rmtree(directorio_temporal, ignore_errors=True)
        raise
    except Exception as error:
        shutil.rmtree(directorio_temporal, ignore_errors=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No se pudieron cargar los XML CFDI",
        ) from error

    job_id = crear_job(directorio_temporal, rutas_xml)
    return {"job_id": job_id, "archivos": nombres}


@router.post("/excel", summary="Genera Excel desde archivos CFDI 4.0")
async def generar_reporte_cfdi(
    background_tasks: BackgroundTasks,
    archivos: list[UploadFile] = File(..., description="Uno o más archivos XML CFDI 4.0"),
) -> FileResponse:
    """Recibe XMLs, devuelve reporte .xlsx y elimina temporales al finalizar."""
    if not archivos:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Envía al menos un XML")
    if len(archivos) > MAX_ARCHIVOS_POR_SOLICITUD:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Máximo {MAX_ARCHIVOS_POR_SOLICITUD} XMLs por solicitud",
        )

    directorio_temporal = Path(tempfile.mkdtemp(prefix="flucito_cfdi_"))
    rutas_xml: list[Path] = []
    try:
        for indice, archivo in enumerate(archivos, start=1):
            nombre = Path(archivo.filename or f"archivo_{indice}.xml").name
            if Path(nombre).suffix.lower() != ".xml":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"{nombre}: solo se aceptan archivos .xml",
                )
            destino = directorio_temporal / f"{indice}_{nombre}"
            await _guardar_xml(archivo, destino)
            rutas_xml.append(destino)

        salida = directorio_temporal / "reporte_cfdi.xlsx"
        await run_in_threadpool(generar_excel_desde_xmls, rutas_xml, salida)
    except HTTPException:
        shutil.rmtree(directorio_temporal, ignore_errors=True)
        raise
    except Exception as error:
        shutil.rmtree(directorio_temporal, ignore_errors=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No se pudo generar reporte CFDI",
        ) from error

    background_tasks.add_task(shutil.rmtree, directorio_temporal, ignore_errors=True)
    return FileResponse(
        path=salida,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename="reporte_cfdi.xlsx",
        background=background_tasks,
    )
