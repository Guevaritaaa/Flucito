"""Rutas para descargar la base acumulativa de entradas de almacén."""

from __future__ import annotations

import logging
import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from app.core.security import obtener_usuario_opcional
from app.models.usuario import Usuario
from app.services.almacen.excel import CARPETA_DATOS, NOMBRE_ARCHIVO_BASE
from app.services.almacen.fuentes.subidor import subir_documentos_drive
from app.services.almacen.fuentes.google_drive_client import (
    buscar_reportes_historicos,
    crear_cliente_drive,
    descargar_archivo,
)
from app.services.almacen.fuentes.google_drive import DriveArchivo
from app.services.almacen.txt_aspel import NOMBRE_TXT_COMAS, NOMBRE_TXT_TABS

logger = logging.getLogger(__name__)

MAX_ARCHIVOS = 150
MAX_BYTES = 20 * 1024 * 1024


router = APIRouter(
    prefix="/almacen",
    tags=["Almacén"],
    dependencies=[Depends(obtener_usuario_opcional)],
)


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
def descargar_txt_almacen(separador: str = "comas", usuario_actual: Usuario | None = Depends(obtener_usuario_opcional)) -> FileResponse:
    """Entrega TXT con comas o tabulaciones según parámetro `separador`."""
    from app.services.revision_reportes import verificar_txt
    verificar_txt(CARPETA_DATOS / NOMBRE_ARCHIVO_BASE, getattr(usuario_actual, "id", None))
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


@router.get("/download/historico", summary="Descarga un reporte histórico de Google Drive")
def descargar_reporte_historico(fecha: str, archivo_id: str) -> FileResponse:
    """Verifica que el reporte pertenezca a la fecha y carpeta configuradas antes de descargarlo."""
    try:
        cliente = crear_cliente_drive()
        reportes = buscar_reportes_historicos(fecha, cliente)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error

    reporte = next((item for item in reportes if item["id"] == archivo_id), None)
    if reporte is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No se encontró ese reporte para la fecha indicada",
        )

    directorio = Path(tempfile.mkdtemp(prefix="flucito_reporte_historico_"))
    destino = directorio / Path(reporte["nombre"]).name
    try:
        descargar_archivo(
            cliente,
            DriveArchivo(
                id=reporte["id"],
                nombre=reporte["nombre"],
                mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                modificado=None,
                carpeta_id="",
            ),
            destino,
        )
    except Exception:
        shutil.rmtree(directorio, ignore_errors=True)
        raise

    return FileResponse(
        path=destino,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=destino.name,
        background=BackgroundTask(shutil.rmtree, directorio, ignore_errors=True),
    )


@router.get("/reportes/{reporte_id}")
def estado_revision(reporte_id: str, session_id: str, usuario_actual: Usuario | None = Depends(obtener_usuario_opcional)):
    from app.services.revision_reportes import cargar, publico
    from app.services import decisiones
    uid = getattr(usuario_actual, "id", None)
    salida = publico(cargar(reporte_id, session_id, uid))
    pendiente = decisiones.leer(session_id, uid)
    if pendiente and pendiente["herramienta"] == "revisar_reporte_almacen" and pendiente["argumentos"].get("reporte_id") == reporte_id and pendiente["argumentos"].get("version") == salida["version"]:
        salida["interaccion"] = pendiente["interaccion"]
    return salida


@router.get("/reportes/{reporte_id}/archivo")
def descargar_revision(reporte_id: str, session_id: str, formato: str = "xlsx", usuario_actual: Usuario | None = Depends(obtener_usuario_opcional)):
    from app.services.revision_reportes import cargar, directorio
    meta = cargar(reporte_id, session_id, getattr(usuario_actual, "id", None))
    if formato == "xlsx":
        ruta = directorio() / (reporte_id + ".xlsx")
        nombre = meta["nombre"]
    elif formato in {"comas", "tabs"}:
        if meta["pendientes"] or meta["estado"] != "validado":
            raise HTTPException(409, "Primero valida los precios del reporte corregido.")
        nombre = Path(meta["nombre"]).stem + "_" + ("COMAS" if formato == "comas" else "TABS") + ".txt"
        ruta = directorio() / reporte_id / nombre
    else:
        raise HTTPException(422, "Formato no válido.")
    if not ruta.is_file():
        raise HTTPException(404, "El archivo ya no está disponible.")
    return FileResponse(ruta, filename=nombre)


@router.post("/reportes/{reporte_id}/validar")
async def validar_revision(reporte_id: str, session_id: str, archivo: UploadFile = File(...), usuario_actual: Usuario | None = Depends(obtener_usuario_opcional)):
    from app.services.revision_reportes import cargar, validar_corregido
    uid = getattr(usuario_actual, "id", None)
    cargar(reporte_id, session_id, uid)
    if Path(archivo.filename or "").suffix.lower() != ".xlsx":
        raise HTTPException(422, "Adjunta el reporte corregido en formato .xlsx.")
    contenido = await archivo.read(MAX_BYTES + 1)
    if len(contenido) > MAX_BYTES:
        raise HTTPException(413, "El archivo supera 20 MB.")
    salida = await run_in_threadpool(validar_corregido, reporte_id, contenido, uid)
    from app.services import decisiones
    from app.schemas.chat import ChatResponse
    from app.api.v1.routes import chat
    if salida.get("factores_pendientes"):
        salida["interaccion"] = decisiones.registrar(session_id, uid,
            {"lineas_sin_factor": salida["factores_pendientes"]}, "revisar_reporte_almacen",
            {"reporte_id": reporte_id, "version": salida["version"]})
    respuesta = ChatResponse(respuesta=salida["resumen_revision"], revision_reporte=salida,
                             interaccion=salida.get("interaccion"))
    mensaje = f"Adjunté el Excel corregido de {salida['nombre']}."
    config = {"configurable": {"thread_id": session_id}}
    if callable(getattr(chat.grafo, "update_state", None)) and chat._memoria_grafo_tiene_mensajes(config):
        from langchain_core.messages import AIMessage, HumanMessage
        chat.grafo.update_state(config, {"messages": [HumanMessage(content=mensaje), AIMessage(content=respuesta.respuesta)]}, as_node="flucito")
    chat._guardar_interaccion_en_bd(session_id=session_id, usuario_id=uid,
        mensaje_usuario=mensaje, respuesta_chat=respuesta)
    return salida


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
