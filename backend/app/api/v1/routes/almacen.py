"""Rutas para descargar la base acumulativa de entradas de almacén."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse

from app.services.almacen.excel import CARPETA_DATOS, NOMBRE_ARCHIVO_BASE
from app.services.almacen.fuentes.subidor import subir_documentos_drive


MAX_ARCHIVOS = 150
MAX_BYTES = 20 * 1024 * 1024


router = APIRouter(prefix="/almacen", tags=["Almacén"])


@router.get("/download", summary="Descarga base de entradas de almacén")
def descargar_base_almacen() -> FileResponse:
    """Entrega la base generada desde la carpeta configurada."""
    ruta = CARPETA_DATOS / NOMBRE_ARCHIVO_BASE
    if not ruta.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
        detail="Base de entradas de almacén no encontrada",
        )

    return FileResponse(
        path=ruta,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=NOMBRE_ARCHIVO_BASE,
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

    directorio = Path(tempfile.mkdtemp(prefix="flucito_almacen_upload_"))
    rutas: list[Path] = []
    try:
        for indice, archivo in enumerate(archivos, start=1):
            nombre = Path(archivo.filename or f"archivo_{indice}").name
            if Path(nombre).suffix.lower() not in {".xml", ".pdf", ".txt"}:
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
        return {"ok": True, **resultado}
    except HTTPException:
        raise
    except (OSError, RuntimeError, ValueError) as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        ) from error
    finally:
        shutil.rmtree(directorio, ignore_errors=True)
