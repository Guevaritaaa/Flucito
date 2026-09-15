"""Rutas para descargar la base acumulativa de entradas de almacén."""

from __future__ import annotations

import logging
import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse

from app.services.almacen.excel import CARPETA_DATOS, NOMBRE_ARCHIVO_BASE
from app.services.almacen.fuentes.subidor import subir_documentos_drive
from app.services.almacen.txt_aspel import NOMBRE_TXT_COMAS, NOMBRE_TXT_TABS

logger = logging.getLogger(__name__)

MAX_ARCHIVOS = 150
MAX_BYTES = 20 * 1024 * 1024


router = APIRouter(prefix="/almacen", tags=["Almacén"])


@router.get("/download", summary="Descarga base de entradas de almacén")
def descargar_base_almacen() -> FileResponse:
    """Entrega la base generada desde la carpeta configurada."""
    ruta = CARPETA_DATOS / NOMBRE_ARCHIVO_BASE
    if not ruta.is_file():
        logger.warning("Intento de descarga de base inexistente en: %s", ruta)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Base de entradas de almacén no encontrada",
        )

    logger.info("Descargando base de entradas: %s", ruta)
    return FileResponse(
        path=ruta,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=NOMBRE_ARCHIVO_BASE,
    )


@router.get("/download/txt", summary="Descarga TXT de entradas (comas por defecto)")
def descargar_txt_almacen(separador: str = "comas") -> FileResponse:
    """Entrega TXT con comas o tabulaciones según parámetro `separador`."""
    if separador == "tabs":
        nombre = NOMBRE_TXT_TABS
    else:
        nombre = NOMBRE_TXT_COMAS

    ruta = CARPETA_DATOS / nombre
    if not ruta.is_file():
        logger.warning("TXT no encontrado: %s", ruta)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Archivo TXT de entradas no encontrado. Genera el reporte primero.",
        )

    logger.info("Descargando TXT: %s", ruta)
    return FileResponse(
        path=ruta,
        media_type="text/plain",
        filename=nombre,
    )


@router.post("/upload", summary="Sube documentos de facturas a Google Drive")
async def cargar_documentos_almacen(
    archivos: list[UploadFile] = File(...),
) -> dict[str, object]:
    """Recibe XML/PDF/TXT, agrupa por factura y los guarda en Drive."""
    if not archivos:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Envía documentos")
    if len(archivos) > MAX_ARCHIVOS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Máximo {MAX_ARCHIVOS} archivos",
        )

    logger.info("Recibidos %d archivo(s) para carga a Google Drive", len(archivos))
    directorio = Path(tempfile.mkdtemp(prefix="flucito_almacen_upload_"))
    rutas: list[Path] = []
    try:
        for indice, archivo in enumerate(archivos, start=1):
            nombre = Path(archivo.filename or f"archivo_{indice}").name
            if Path(nombre).suffix.lower() not in {".xml", ".pdf", ".txt"}:
                logger.warning("Tipo de archivo no soportado rechazado: %s", nombre)
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"{nombre}: tipo no soportado",
                )
            destino = directorio / nombre
            total = 0
            with destino.open("wb") as salida:
                while bloque := await archivo.read(1024 * 1024):
                    total += len(bloque)
                    if total > MAX_BYTES:
                        raise HTTPException(
                            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            detail=f"{nombre}: supera 20 MB",
                        )
                    salida.write(bloque)
            await archivo.close()
            rutas.append(destino)

        resultado = await run_in_threadpool(subir_documentos_drive, rutas)
        logger.info("Carga a Drive completada exitosamente: %s", resultado)
        return {"ok": True, **resultado}
    except HTTPException:
        raise
    except (OSError, RuntimeError, ValueError) as error:
        logger.exception("Error al subir documentos a Drive: %s", error)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        ) from error
    finally:
        shutil.rmtree(directorio, ignore_errors=True)
