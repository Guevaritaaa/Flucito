import json
import logging
import threading
import time
import uuid
from typing import Any
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException
from langchain_core.messages import HumanMessage

from app.agents.graph import grafo
from app.schemas.chat import (
    ChatJobCreateResponse,
    ChatJobStatusResponse,
    ChatRequest,
    ChatResponse,
)
from app.services.almacen.excel import CARPETA_DATOS, NOMBRE_ARCHIVO_BASE
from app.services.almacen.txt_aspel import NOMBRE_TXT_COMAS, NOMBRE_TXT_TABS


router = APIRouter()
logger = logging.getLogger(__name__)

_JOBS: dict[str, dict[str, Any]] = {}
_JOBS_LOCK = threading.Lock()
_JOB_TTL_SECONDS = 3600


def _limpiar_jobs_expirados() -> None:
    ahora = time.time()
    with _JOBS_LOCK:
        expirados = [
            jid
            for jid, info in _JOBS.items()
            if info.get("status") in ("completed", "failed")
            and ahora - info.get("created_at", ahora) > _JOB_TTL_SECONDS
        ]
        for jid in expirados:
            _JOBS.pop(jid, None)


def contenido_a_texto(mensaje) -> str:
    """Normaliza respuestas string y bloques de Responses API."""
    texto = getattr(mensaje, "text", None)
    if isinstance(texto, str):
        return texto

    contenido = getattr(mensaje, "content", "")
    return contenido if isinstance(contenido, str) else str(contenido)


def _ejecutar_chat(request: ChatRequest) -> ChatResponse:
    """Ejecuta el grafo conversacional y construye el ChatResponse."""
    estado = {"messages": [HumanMessage(content=request.mensaje)]}
    config = {"configurable": {"thread_id": request.session_id}}
    resultado = grafo.invoke(estado, config=config)
    respuesta = contenido_a_texto(resultado["messages"][-1])

    archivo_almacen_url = None
    reportes_historicos: list[dict[str, str]] = []
    advertencia_ubicacion: str | None = None
    advertencia_archivos_sueltos: str | None = None
    for mensaje in reversed(resultado["messages"]):
        tipo_mensaje = getattr(mensaje, "type", None)
        if tipo_mensaje == "human":
            break
        if tipo_mensaje != "tool":
            continue
        try:
            datos = json.loads(mensaje.content)
        except (TypeError, json.JSONDecodeError):
            continue
        if datos.get("ok") and datos.get("tipo") == "busqueda_historica" and not reportes_historicos:
            reportes_historicos = [
                {
                    "nombre": reporte["nombre"],
                    "fecha": reporte["fecha"],
                    "url": "/api/v1/almacen/download/historico?"
                    + urlencode({"fecha": reporte["fecha"], "archivo_id": reporte["id"]}),
                }
                for reporte in datos.get("reportes", [])
            ]
        if datos.get("ok") and datos.get("tipo") == "ordenar_todo":
            if datos.get("advertencia_archivos_sueltos") and not advertencia_archivos_sueltos:
                advertencia_archivos_sueltos = str(datos["advertencia_archivos_sueltos"])
        if datos.get("ok") and datos.get("reporte_generado") and datos.get("resumen"):
            archivo_almacen_url = "/api/v1/almacen/download"
            if datos.get("advertencia_ubicacion") and not advertencia_ubicacion:
                advertencia_ubicacion = str(datos["advertencia_ubicacion"])

    if (
        advertencia_ubicacion
        and "mal ubicadas" not in respuesta.lower()
        and "recuerda que para subir documentos a procesar" not in respuesta.lower()
    ):
        respuesta = f"{advertencia_ubicacion}\n\n{respuesta}"

    if (
        advertencia_archivos_sueltos
        and "archivos sueltos" not in respuesta.lower()
        and "organiza manualmente" not in respuesta.lower()
    ):
        respuesta = f"{respuesta}\n\n{advertencia_archivos_sueltos}"

    # Si la base física existe y el asistente la menciona o el usuario la pidió
    if archivo_almacen_url is None and (CARPETA_DATOS / NOMBRE_ARCHIVO_BASE).is_file():
        palabras_clave = ("descarg", "botón", "boton", "archivo excel", "plataforma", "portal")
        if any(p in respuesta.lower() for p in palabras_clave):
            archivo_almacen_url = "/api/v1/almacen/download"

    # Detectar si el asistente ofrece/menciona TXT y agregar URLs de descarga
    archivo_txt_url = None
    resp_lower = respuesta.lower()
    txt_detectado = any(p in resp_lower for p in ("txt", "tabulacion", "comas", "aspel"))
    if txt_detectado:
        if "tabulacion" in resp_lower and (CARPETA_DATOS / NOMBRE_TXT_TABS).is_file():
            archivo_txt_url = "/api/v1/almacen/download/txt?separador=tabs"
        elif (CARPETA_DATOS / NOMBRE_TXT_COMAS).is_file():
            archivo_txt_url = "/api/v1/almacen/download/txt?separador=comas"

    return ChatResponse(
        respuesta=respuesta,
        archivo_almacen_url=archivo_almacen_url,
        archivo_txt_url=archivo_txt_url,
        reportes_historicos=reportes_historicos,
    )


def _trabajador_chat(job_id: str, request: ChatRequest) -> None:
    try:
        respuesta = _ejecutar_chat(request)
        with _JOBS_LOCK:
            if job_id in _JOBS:
                _JOBS[job_id]["status"] = "completed"
                _JOBS[job_id]["result"] = respuesta
    except Exception as exc:
        logger.exception("Error procesando tarea de chat %s", job_id)
        with _JOBS_LOCK:
            if job_id in _JOBS:
                _JOBS[job_id]["status"] = "failed"
                _JOBS[job_id]["error"] = str(exc)


@router.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    """Procesa conversación del asistente y devuelve enlace de almacén."""
    return _ejecutar_chat(request)


@router.post("/chat/async", response_model=ChatJobCreateResponse)
def iniciar_chat_async(request: ChatRequest) -> ChatJobCreateResponse:
    """Inicia una conversación en segundo plano para evitar timeouts HTTP (Cloudflare 524)."""
    _limpiar_jobs_expirados()
    job_id = str(uuid.uuid4())
    with _JOBS_LOCK:
        _JOBS[job_id] = {
            "status": "running",
            "created_at": time.time(),
            "result": None,
            "error": None,
        }
    hilo = threading.Thread(target=_trabajador_chat, args=(job_id, request), daemon=True)
    hilo.start()
    return ChatJobCreateResponse(job_id=job_id, status="running")


@router.get("/chat/status/{job_id}", response_model=ChatJobStatusResponse)
def consultar_estado_chat(job_id: str) -> ChatJobStatusResponse:
    """Consulta el estado de una tarea de chat iniciada con /chat/async."""
    with _JOBS_LOCK:
        job = _JOBS.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Tarea de chat no encontrada")
        return ChatJobStatusResponse(
            job_id=job_id,
            status=job["status"],
            result=job["result"],
            error=job["error"],
        )

