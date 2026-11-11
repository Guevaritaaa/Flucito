from datetime import datetime, timezone
import json
import logging
import re
import threading
import time
from typing import Any
from urllib.parse import urlencode
import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from langchain_core.messages import AIMessage, HumanMessage
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agents.graph import grafo
from app.core.database import Base, SessionLocal, engine, get_db
from app.core.security import obtener_usuario_actual, obtener_usuario_opcional
from app.models.conversacion import Conversacion, MensajeChat
from app.models.usuario import Usuario
from app.schemas.chat import (
    ChatJobCreateResponse,
    ChatJobStatusResponse,
    ChatRequest,
    ChatResponse,
    ConversacionDetalleOut,
    ConversacionResumenOut,
    MensajeChatOut,
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


def _generar_titulo_conversacion(mensaje: str) -> str:
    limpio = " ".join((mensaje or "").strip().split())
    if not limpio:
        return "Nueva conversación"
    return limpio[:80] + ("..." if len(limpio) > 80 else "")


def _obtener_mensajes_previos_bd(session_id: str, usuario_id: int | None) -> list[Any]:
    """
    Verifica permisos de la conversación y devuelve los mensajes previos guardados en BD
    para reconstruir el contexto de LangGraph si el servidor se reinició.
    """
    try:
        Base.metadata.create_all(bind=engine)
        with SessionLocal() as db:
            conv = db.scalar(select(Conversacion).where(Conversacion.id == session_id))
            if conv is None:
                return []
            if conv.usuario_id is not None and usuario_id is not None and conv.usuario_id != usuario_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="No tienes permiso para acceder a una conversación de otro usuario.",
                )
            filas = db.scalars(
                select(MensajeChat)
                .where(MensajeChat.conversacion_id == session_id)
                .order_by(MensajeChat.id.asc())
            ).all()
            historial = []
            for fila in filas:
                if fila.rol == "user":
                    historial.append(HumanMessage(content=fila.contenido))
                elif fila.rol == "assistant":
                    historial.append(AIMessage(content=fila.contenido))
            return historial
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("No se pudo leer historial previo de BD para %s: %s", session_id, exc)
        return []


def _guardar_interaccion_en_bd(
    *,
    session_id: str,
    usuario_id: int | None,
    mensaje_usuario: str,
    respuesta_chat: ChatResponse,
) -> None:
    """Guarda la conversación y los mensajes del usuario y de Flucito en la base de datos."""
    try:
        Base.metadata.create_all(bind=engine)
        ahora = datetime.now(timezone.utc)
        with SessionLocal() as db:
            conv = db.scalar(select(Conversacion).where(Conversacion.id == session_id))
            if conv is None:
                conv = Conversacion(
                    id=session_id,
                    usuario_id=usuario_id,
                    titulo=_generar_titulo_conversacion(mensaje_usuario),
                    creada_en=ahora,
                    actualizada_en=ahora,
                )
                db.add(conv)
            else:
                if conv.usuario_id is None and usuario_id is not None:
                    conv.usuario_id = usuario_id
                conv.actualizada_en = ahora

            db.add(
                MensajeChat(
                    conversacion_id=session_id,
                    rol="user",
                    contenido=mensaje_usuario,
                    metadatos_json=None,
                    creado_en=ahora,
                )
            )
            metadatos = {
                "archivo_almacen_url": respuesta_chat.archivo_almacen_url,
                "archivo_txt_url": respuesta_chat.archivo_txt_url,
                "reportes_historicos": respuesta_chat.reportes_historicos,
            }
            db.add(
                MensajeChat(
                    conversacion_id=session_id,
                    rol="assistant",
                    contenido=respuesta_chat.respuesta,
                    metadatos_json=json.dumps(metadatos, ensure_ascii=False),
                    creado_en=ahora,
                )
            )
            db.commit()
    except Exception as exc:
        logger.warning("No se pudo guardar la conversación %s en BD: %s", session_id, exc)


def _memoria_grafo_tiene_mensajes(config: dict[str, Any]) -> bool:
    getter = getattr(grafo, "get_state", None)
    if not callable(getter):
        return True
    try:
        estado_actual = getter(config)
        valores = getattr(estado_actual, "values", None) or {}
        mensajes = valores.get("messages") if isinstance(valores, dict) else None
        return bool(mensajes)
    except Exception:
        return True


def _ejecutar_chat(request: ChatRequest, usuario_id: int | None = None) -> ChatResponse:
    """Ejecuta el grafo conversacional, construye el ChatResponse y lo persiste en BD."""
    mensajes_previos = _obtener_mensajes_previos_bd(request.session_id, usuario_id)
    config = {"configurable": {"thread_id": request.session_id}}

    if mensajes_previos and not _memoria_grafo_tiene_mensajes(config):
        estado = {"messages": [*mensajes_previos, HumanMessage(content=request.mensaje)]}
    else:
        estado = {"messages": [HumanMessage(content=request.mensaje)]}

    try:
        resultado = grafo.invoke(estado, config=config)
    except Exception as error_grafo:
        logger.warning(
            "Fallo en grafo.invoke para sesión %s (%s); reintentando con hilo limpio.",
            request.session_id,
            error_grafo,
        )
        try:
            config_limpio = {
                "configurable": {
                    "thread_id": f"{request.session_id}-recovery-{uuid.uuid4().hex[:8]}"
                }
            }
            resultado = grafo.invoke(estado, config=config_limpio)
        except Exception as error_final:
            logger.exception("Error definitivo en grafo.invoke: %s", error_final)
            return ChatResponse(
                respuesta=(
                    "Ocurrió una interrupción temporal al procesar tu solicitud. "
                    "Por favor intenta enviarla nuevamente en unos segundos."
                ),
            )

    respuesta = contenido_a_texto(resultado["messages"][-1])

    archivo_almacen_url = None
    reportes_historicos: list[dict[str, str]] = []
    advertencia_ubicacion: str | None = None
    advertencia_archivos_sueltos: str | None = None
    advertencia_xmls_sin_apoyo: str | None = None
    advertencia_productos_regalo: str | None = None
    bloqueado_por_confirmacion = False
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
        if datos.get("requiere_confirmacion") or datos.get("cancelado_por_usuario"):
            bloqueado_por_confirmacion = True
        if datos.get("ok") and datos.get("tipo") == "busqueda_historica" and not reportes_historicos:
            lista_rep = datos.get("reportes", [])
            if (
                not datos.get("fecha")
                and lista_rep
                and re.search(r"\b(ultimo|último|reciente|recientes)\b", request.mensaje, re.IGNORECASE)
            ):
                fecha_mas_reciente = lista_rep[0].get("fecha")
                lista_rep = [r for r in lista_rep if r.get("fecha") == fecha_mas_reciente]
            reportes_historicos = [
                {
                    "nombre": reporte["nombre"],
                    "fecha": reporte["fecha"],
                    "url": "/api/v1/almacen/download/historico?"
                    + urlencode({"fecha": reporte["fecha"], "archivo_id": reporte["id"]}),
                }
                for reporte in lista_rep
            ]
        if datos.get("ok") and datos.get("tipo") == "ordenar_todo":
            if datos.get("advertencia_archivos_sueltos") and not advertencia_archivos_sueltos:
                advertencia_archivos_sueltos = str(datos["advertencia_archivos_sueltos"])
        if datos.get("ok") and datos.get("advertencia_ubicacion") and not advertencia_ubicacion:
            advertencia_ubicacion = str(datos["advertencia_ubicacion"])
        if datos.get("ok") and datos.get("advertencia_xmls_sin_apoyo") and not advertencia_xmls_sin_apoyo:
            advertencia_xmls_sin_apoyo = str(datos["advertencia_xmls_sin_apoyo"])
        aviso_regalo = datos.get("advertencia_productos_regalo") or (
            (datos.get("resumen") or {}).get("advertencia_productos_regalo")
            if isinstance(datos.get("resumen"), dict)
            else None
        )
        if datos.get("ok") and aviso_regalo and not advertencia_productos_regalo:
            advertencia_productos_regalo = str(aviso_regalo)
        if (
            datos.get("ok")
            and datos.get("tipo") == "actualizar_precios_reportes"
            and datos.get("base_local_actualizada")
            and (CARPETA_DATOS / NOMBRE_ARCHIVO_BASE).is_file()
        ):
            archivo_almacen_url = "/api/v1/almacen/download"
        if datos.get("ok") and datos.get("reporte_generado") and datos.get("resumen"):
            archivo_almacen_url = "/api/v1/almacen/download"

    resp_lower_check = respuesta.lower()
    ya_incluye_aviso_ubicacion = any(
        frase in resp_lower_check
        for frase in (
            "mal ubicadas",
            "moví automáticamente",
            "movi automaticamente",
            "fue movida de",
            "fueron movidas de",
            "reubicad",
            "no tenían su reporte generado",
            "no tenía su reporte generado",
            "recuerda que para subir documentos a procesar",
            "facturas pendientes",
        )
    )
    if advertencia_ubicacion and not ya_incluye_aviso_ubicacion:
        respuesta = f"{advertencia_ubicacion}\n\n{respuesta}"

    if (
        advertencia_archivos_sueltos
        and "archivos sueltos" not in respuesta.lower()
        and "organiza manualmente" not in respuesta.lower()
    ):
        respuesta = f"{respuesta}\n\n{advertencia_archivos_sueltos}"

    if (
        advertencia_xmls_sin_apoyo
        and "sin archivo de apoyo" not in respuesta.lower()
    ):
        respuesta = f"{respuesta}\n\n{advertencia_xmls_sin_apoyo}"

    if (
        advertencia_productos_regalo
        and "regalado" not in respuesta.lower()
        and "regalo" not in respuesta.lower()
    ):
        respuesta = f"{respuesta}\n\n{advertencia_productos_regalo}"

    # Si la base física existe y el asistente la menciona o el usuario la pidió
    if (
        not bloqueado_por_confirmacion
        and archivo_almacen_url is None
        and (CARPETA_DATOS / NOMBRE_ARCHIVO_BASE).is_file()
    ):
        palabras_clave = ("descarg", "botón", "boton", "archivo excel", "plataforma", "portal")
        if any(p in respuesta.lower() for p in palabras_clave):
            archivo_almacen_url = "/api/v1/almacen/download"

    # Detectar si el asistente ofrece/menciona el TXT de salida para Aspel (evitando falsos positivos por "TXT de apoyo")
    archivo_txt_url = None
    resp_lower = respuesta.lower()
    menciona_txt_aspel = any(
        frase in resp_lower
        for frase in (
            "aspel",
            "tabulacion",
            "tabulación",
            "separado por comas",
            "separador de comas",
            "descargar txt",
            "descargar el txt",
            "archivo txt de salida",
        )
    ) or (archivo_almacen_url is not None and "txt" in resp_lower)
    if not bloqueado_por_confirmacion and menciona_txt_aspel:
        if ("tabulacion" in resp_lower or "tabulación" in resp_lower) and (
            CARPETA_DATOS / NOMBRE_TXT_TABS
        ).is_file():
            archivo_txt_url = "/api/v1/almacen/download/txt?separador=tabs"
        elif (CARPETA_DATOS / NOMBRE_TXT_COMAS).is_file():
            archivo_txt_url = "/api/v1/almacen/download/txt?separador=comas"

    respuesta_final = ChatResponse(
        respuesta=respuesta,
        archivo_almacen_url=archivo_almacen_url,
        archivo_txt_url=archivo_txt_url,
        reportes_historicos=reportes_historicos,
    )
    _guardar_interaccion_en_bd(
        session_id=request.session_id,
        usuario_id=usuario_id,
        mensaje_usuario=request.mensaje,
        respuesta_chat=respuesta_final,
    )
    return respuesta_final


def _trabajador_chat(job_id: str, request: ChatRequest, usuario_id: int | None = None) -> None:
    try:
        if usuario_id is None:
            respuesta = _ejecutar_chat(request)
        else:
            respuesta = _ejecutar_chat(request, usuario_id=usuario_id)
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
def chat(
    request: ChatRequest,
    usuario_actual: Usuario | None = Depends(obtener_usuario_opcional),
) -> ChatResponse:
    """Procesa conversación del asistente, la asocia al usuario y devuelve enlace de almacén."""
    uid = getattr(usuario_actual, "id", None)
    if uid is None:
        return _ejecutar_chat(request)
    return _ejecutar_chat(request, usuario_id=uid)


@router.post("/chat/async", response_model=ChatJobCreateResponse)
def iniciar_chat_async(
    request: ChatRequest,
    usuario_actual: Usuario | None = Depends(obtener_usuario_opcional),
) -> ChatJobCreateResponse:
    """Inicia una conversación en segundo plano para evitar timeouts HTTP (Cloudflare 524)."""
    uid = getattr(usuario_actual, "id", None)
    _limpiar_jobs_expirados()
    job_id = str(uuid.uuid4())
    with _JOBS_LOCK:
        _JOBS[job_id] = {
            "status": "running",
            "created_at": time.time(),
            "result": None,
            "error": None,
        }
    hilo = threading.Thread(target=_trabajador_chat, args=(job_id, request, uid), daemon=True)
    hilo.start()
    return ChatJobCreateResponse(job_id=job_id, status="running")


@router.get("/chat/status/{job_id}", response_model=ChatJobStatusResponse)
def consultar_estado_chat(
    job_id: str,
    usuario_actual: Usuario | None = Depends(obtener_usuario_opcional),
) -> ChatJobStatusResponse:
    """Consulta el estado de una tarea de chat iniciada con /chat/async."""
    _ = usuario_actual
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


@router.get(
    "/chat/conversaciones",
    response_model=list[ConversacionResumenOut],
    summary="Lista todas las conversaciones guardadas del usuario autenticado",
)
def listar_conversaciones_usuario(
    usuario_actual: Usuario = Depends(obtener_usuario_actual),
    db: Session = Depends(get_db),
) -> list[ConversacionResumenOut]:
    """Devuelve las conversaciones del usuario ordenadas de la más reciente a la más antigua."""
    conversaciones = db.scalars(
        select(Conversacion)
        .where(Conversacion.usuario_id == usuario_actual.id)
        .order_by(Conversacion.actualizada_en.desc())
    ).all()

    salida: list[ConversacionResumenOut] = []
    for conv in conversaciones:
        total_msgs = (
            db.scalar(
                select(func.count())
                .select_from(MensajeChat)
                .where(MensajeChat.conversacion_id == conv.id)
            )
            or 0
        )
        salida.append(
            ConversacionResumenOut(
                id=conv.id,
                usuario_id=conv.usuario_id,
                titulo=conv.titulo,
                creada_en=conv.creada_en,
                actualizada_en=conv.actualizada_en,
                total_mensajes=int(total_msgs),
            )
        )
    return salida


@router.get(
    "/chat/conversaciones/{session_id}",
    response_model=ConversacionDetalleOut,
    summary="Obtiene todos los mensajes de una conversación del usuario",
)
def obtener_detalle_conversacion(
    session_id: str,
    usuario_actual: Usuario = Depends(obtener_usuario_actual),
    db: Session = Depends(get_db),
) -> ConversacionDetalleOut:
    """Devuelve los mensajes completos de una conversación verificando su dueño."""
    conv = db.scalar(select(Conversacion).where(Conversacion.id == session_id))
    if conv is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversación no encontrada.",
        )
    if conv.usuario_id != usuario_actual.id and usuario_actual.rol != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permiso para ver esta conversación.",
        )

    mensajes_out: list[MensajeChatOut] = []
    for msg in conv.mensajes:
        meta: dict[str, Any] = {}
        if msg.metadatos_json:
            try:
                meta = json.loads(msg.metadatos_json)
            except json.JSONDecodeError:
                meta = {}
        mensajes_out.append(
            MensajeChatOut(
                id=msg.id,
                rol=msg.rol,
                contenido=msg.contenido,
                archivo_almacen_url=meta.get("archivo_almacen_url"),
                archivo_txt_url=meta.get("archivo_txt_url"),
                reportes_historicos=meta.get("reportes_historicos") or [],
                creado_en=msg.creado_en,
            )
        )

    return ConversacionDetalleOut(
        id=conv.id,
        usuario_id=conv.usuario_id,
        titulo=conv.titulo,
        creada_en=conv.creada_en,
        actualizada_en=conv.actualizada_en,
        mensajes=mensajes_out,
    )


@router.delete(
    "/chat/conversaciones/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Elimina una conversación y sus mensajes del historial del usuario",
)
def eliminar_conversacion(
    session_id: str,
    usuario_actual: Usuario = Depends(obtener_usuario_actual),
    db: Session = Depends(get_db),
) -> Response:
    """Borra una conversación perteneciente al usuario autenticado."""
    conv = db.scalar(select(Conversacion).where(Conversacion.id == session_id))
    if conv is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversación no encontrada.",
        )
    if conv.usuario_id != usuario_actual.id and usuario_actual.rol != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permiso para eliminar esta conversación.",
        )
    db.delete(conv)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
