from datetime import datetime, timezone
import asyncio
import json
import logging
import re
import threading
import time
from typing import Any
from urllib.parse import urlencode
import uuid
from copy import deepcopy

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.callbacks import BaseCallbackHandler
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agents.graph import grafo
from app.agents.actividad import PASOS, ESTADOS
from app.services.almacen.fuentes.operaciones_drive import recuperar as recuperar_operaciones_drive
from app.core.database import Base, SessionLocal, engine, get_db
from app.core.config import settings
from app.core.security import obtener_usuario_actual, obtener_usuario_opcional
from app.models.conversacion import Conversacion, MensajeChat
from app.models.usuario import Usuario
from app.schemas.decisiones import EnvioDecisiones
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
from app.services.almacen.resumen import explicar_procedencia_reporte
from app.services.almacen.fuentes.google_drive_client import normalizar_fecha_reporte


router = APIRouter()
logger = logging.getLogger(__name__)

_JOBS: dict[str, dict[str, Any]] = {}
_JOBS_LOCK = threading.Lock()
_JOB_TTL_SECONDS = 3600
_CONTEXTO_JOB = threading.local()
_NOMBRES_HERRAMIENTAS = {
    "consultar_drive": "Consultando Drive",
    "gestionar_archivos_drive": "Organizando archivos en Drive",
    "consultar_almacen": "Consultando almacén",
    "generar_entradas_almacen": "Generando reporte de almacén",
    "actualizar_precios_reportes_generados": "Actualizando precios de reportes",
    "preparar_entorno_pruebas": "Preparando el entorno de pruebas",
}


class ActividadHandler(BaseCallbackHandler):
    """Registra solo etapas y nombres conocidos, nunca entradas ni resultados."""

    def __init__(self, job_id: str | None = None):
        self.job_id = job_id
        self.lock = threading.Lock()
        self.actividades: list[dict[str, str]] = []
        self.runs: dict[str, int] = {}
        self.etapa = "pensando"
        self.texto_provisional = ""
        self.runs_con_tools: set[str] = set()
        self.reintentos: dict[str, int] = {}
        self.resultados_drive: list[dict] = []
        self.pasos: dict[str, int] = {}
        self.resumenes_en_curso: dict[str, dict[tuple, str]] = {}

    def _resumen_chunk(self, mensaje, run_id):
        bloques = getattr(mensaje, "content", None)
        if not isinstance(bloques, list):
            return
        with self.lock:
            partes = self.resumenes_en_curso.setdefault(str(run_id), {})
            for bloque in bloques:
                if isinstance(bloque, dict) and bloque.get("type") == "reasoning":
                    for resumen in bloque.get("summary", []):
                        if isinstance(resumen, dict) and resumen.get("type") == "summary_text" and isinstance(resumen.get("text"), str):
                            clave = (bloque.get("index", 0), resumen.get("index", 0))
                            partes[clave] = partes.get(clave, "") + resumen["text"]
            indice = self.runs.get(str(run_id))
            if partes and indice is not None and not settings.traducir_resumen_groq:
                self.actividades[indice]["resumen"] = "\n".join(partes[k] for k in sorted(partes))
                self._publicar()

    def on_custom_event(self, name, data, *, run_id, **kwargs):
        if name != "flucito_paso" or data.get("paso") not in PASOS or data.get("estado") not in ESTADOS:
            return
        with self.lock:
            id = data["id"]
            if id not in self.pasos:
                self.pasos[id] = len(self.actividades)
                self.actividades.append({"id": id, "tipo": "accion", "texto": PASOS[data["paso"]], "estado": data["estado"], "funcion": None})
            else:
                self.actividades[self.pasos[id]]["estado"] = data["estado"]
            self.etapa = "trabajando"
            self._publicar()

    def _guardar_resumen(self, mensaje, run_id):
        partes = []
        if isinstance(getattr(mensaje, "content", None), list):
            for bloque in mensaje.content:
                if isinstance(bloque, dict) and bloque.get("type") == "reasoning":
                    partes.extend(p["text"] for p in bloque.get("summary", []) if isinstance(p, dict) and p.get("type") == "summary_text" and isinstance(p.get("text"), str))
        if partes:
            from app.agents.traduccion_resumen import traducir_resumen
            resumen_original = "\n".join(partes)
            resumen, origen = traducir_resumen(resumen_original) if settings.traducir_resumen_groq else (resumen_original, "original")
            with self.lock:
                indice = self.runs.get(str(run_id))
                if indice is not None:
                    self.actividades[indice]["resumen"] = resumen
                    self.actividades[indice]["resumen_idioma"] = origen
                    self._publicar()

    def _publicar(self):
        if self.job_id:
            with _JOBS_LOCK:
                job = _JOBS.get(self.job_id)
                if job is not None:
                    job["etapa"] = self.etapa
                    job["actividades"] = [dict(item) for item in self.actividades]
                    job["texto_provisional"] = self.texto_provisional

    def _iniciar(self, run_id, texto: str, etapa: str, funcion: str | None = None):
        with self.lock:
            self.etapa = etapa
            self.runs[str(run_id)] = len(self.actividades)
            self.texto_provisional = ""
            self.actividades.append({"id": str(run_id), "tipo": "funcion" if funcion else "modelo", "funcion": funcion, "texto": texto, "estado": "en_curso"})
            self._publicar()

    def _terminar(self, run_id, estado: str):
        with self.lock:
            indice = self.runs.pop(str(run_id), None)
            if indice is not None:
                self.actividades[indice]["estado"] = estado
            if not self.runs:
                self.etapa = "pensando"
            self._publicar()

    def on_chat_model_start(self, serialized, messages, *, run_id, **kwargs):
        with self.lock:
            if self.actividades and self.actividades[-1].get("tipo") == "modelo" and self.actividades[-1].get("estado") == "error":
                indice = len(self.actividades) - 1
                self.actividades[indice]["estado"] = "reintentando"
                self.reintentos[str(run_id)] = indice
        self._iniciar(run_id, "Analizando la solicitud", "pensando")

    def on_llm_end(self, response, *, run_id, **kwargs):
        generaciones = getattr(response, "generations", [])
        mensaje = getattr(generaciones[0][0], "message", None) if generaciones and generaciones[0] else None
        self._guardar_resumen(mensaje, run_id)
        if mensaje is not None:
            with self.lock:
                self.texto_provisional = "" if getattr(mensaje, "tool_calls", None) else contenido_a_texto(mensaje)
                self._publicar()
        with self.lock:
            indice = self.reintentos.pop(str(run_id), None)
            if indice is not None:
                self.actividades[indice]["estado"] = "recuperado"
        self._terminar(run_id, "completado")

    def on_llm_error(self, error, *, run_id, **kwargs):
        with self.lock:
            self.texto_provisional = ""
            indice = self.reintentos.pop(str(run_id), None)
            if indice is not None:
                self.actividades[indice]["estado"] = "error"
            self._publicar()
        self._terminar(run_id, "error")

    def on_llm_new_token(self, token, *, run_id, chunk=None, **kwargs):
        mensaje = getattr(chunk, "message", None)
        self._resumen_chunk(mensaje, run_id)
        with self.lock:
            if getattr(mensaje, "tool_call_chunks", None) or getattr(mensaje, "tool_calls", None):
                self.runs_con_tools.add(str(run_id))
                self.texto_provisional = ""
            elif str(run_id) not in self.runs_con_tools and isinstance(token, str):
                bloques = getattr(mensaje, "content", None)
                if not isinstance(bloques, list) or any(isinstance(b, str) or b.get("type") in {"text", "output_text"} for b in bloques if isinstance(b, (str, dict))):
                    self.texto_provisional += token
            self._publicar()

    def on_tool_start(self, serialized, input_str, *, run_id, name=None, **kwargs):
        nombre = name or (serialized or {}).get("name", "")
        nombre_seguro = nombre if nombre in _NOMBRES_HERRAMIENTAS else None
        self._iniciar(run_id, _NOMBRES_HERRAMIENTAS.get(nombre, "Procesando información"), "trabajando", nombre_seguro)

    def on_tool_end(self, output, *, run_id, **kwargs):
        estado = "error" if getattr(output, "status", None) == "error" else "completado"
        try:
            datos = json.loads(getattr(output, "content", output))
            if isinstance(datos, dict):
                if datos.get("estado") in {"parcial", "pendiente_verificar"}:
                    estado = datos["estado"]
                elif datos.get("requiere_confirmacion"):
                    estado = "pendiente_verificar"
                elif datos.get("ok") is False:
                    estado = "error"
            if isinstance(datos, dict) and (datos.get("requiere_confirmacion") or datos.get("tipo") in {"mover_elemento", "restablecer_carpeta"}):
                with self.lock:
                    self.resultados_drive.append(datos)
        except (TypeError, ValueError):
            pass
        self._terminar(run_id, estado)

    def on_tool_error(self, error, *, run_id, **kwargs):
        self._terminar(run_id, "error")



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
    if isinstance(texto, str) and texto:
        return texto

    contenido = getattr(mensaje, "content", "")
    if isinstance(contenido, str):
        return contenido
    if isinstance(contenido, list):
        partes = []
        for bloque in contenido:
            if isinstance(bloque, str):
                partes.append(bloque)
            elif isinstance(bloque, dict):
                if bloque.get("type") in {"text", "output_text"}:
                    partes.append(bloque.get("text", ""))
                elif bloque.get("type") == "refusal":
                    partes.append(bloque.get("refusal", ""))
        return "".join(partes)
    return ""


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
    from app.services.almacen.avisos import avisos_estado
    if not respuesta_chat.avisos:
        respuesta_chat.avisos = avisos_estado(respuesta_chat.interaccion, respuesta_chat.revision_reporte)
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
                "avisos": respuesta_chat.avisos,
                "interaccion": respuesta_chat.interaccion,
                "revision_reporte": respuesta_chat.revision_reporte,
                "archivo_almacen_url": respuesta_chat.archivo_almacen_url,
                "archivo_txt_url": respuesta_chat.archivo_txt_url,
                "reportes_historicos": respuesta_chat.reportes_historicos,
                "actividades": [a.model_dump() for a in respuesta_chat.actividades],
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


def _tabla_factores(factores: dict[str, dict[str, str]]) -> str:
    columnas = ("PUBLICO", "MINIMO", "MOSTRADOR", "MAYOREO", "DISTRIBUIDOR")
    filas = ["**Factores de precio actuales**", "", "| Factor | Público | Mínimo | Mostrador | Mayoreo | Distribuidor |", "| --- | --- | --- | --- | --- | --- |"]
    for nombre, formulas in factores.items():
        valores = [str(formulas.get(c, "—")).replace("{COSTEO}", "COSTO").replace("{PUBLICO}", "PUBLICO") for c in columnas]
        filas.append("| " + nombre.replace("|", "\\|") + " | " + " | ".join(f"`{v}`" for v in valores) + " |")
    filas.append("\n**Sin factor:** los precios se dejan en `0`.")
    return "\n".join(filas)


def _solicita_descarga(texto: str, formato: str) -> bool:
    texto = texto.lower()
    accion = re.search(r"\b(descarg\w*|baj\w*|env[ií]a\w*|dame|quiero|necesito|p[aá]same|obtener)\b", texto)
    tipo = re.search(r"\b(txt|archivo de texto|tabulaciones|tabs|comas)\b" if formato == "txt" else r"\b(excel|xlsx|archivo de almac[eé]n|reporte)\b", texto)
    return bool(accion and tipo)


def _ejecutar_chat_impl(request: ChatRequest, usuario_id: int | None = None) -> ChatResponse:
    """Ejecuta el grafo conversacional, construye el ChatResponse y lo persiste en BD."""
    mensajes_previos = _obtener_mensajes_previos_bd(request.session_id, usuario_id)
    actividad = ActividadHandler(getattr(_CONTEXTO_JOB, "job_id", None))
    drive_request_id = uuid.uuid4().hex
    config = {"configurable": {"thread_id": request.session_id, "drive_request_id": drive_request_id}, "callbacks": [actividad]}

    def respuesta_guardada():
        texto = recuperar_operaciones_drive(drive_request_id)
        detalles = []
        for datos in actividad.resultados_drive:
            if datos.get("requiere_confirmacion"):
                detalles.append(datos.get("mensaje", "Se necesita tu elección antes de continuar."))
                detalles.extend(f"{c['ruta_completa']} — id:{c['id']}" for c in datos.get("candidatos", []))
            elif not datos.get("ok"):
                detalles.append(datos.get("mensaje") or "La operación no se completó: " + datos.get("error", "sin cambio confirmado"))
        return "\n".join(filter(None, [texto, *detalles]))

    if mensajes_previos and not _memoria_grafo_tiene_mensajes(config):
        estado = {"messages": [*mensajes_previos, HumanMessage(content=request.mensaje)]}
    else:
        estado = {"messages": [HumanMessage(content=request.mensaje)]}

    def ejecutar_grafo(config_actual):
        # El modo messages activa el streaming del modelo dentro del grafo;
        # values conserva el estado final necesario para procesar adjuntos.
        if actividad.job_id and callable(getattr(grafo, "stream", None)):
            ultimo = None
            for modo, contenido in grafo.stream(estado, config=config_actual, stream_mode=["messages", "values"]):
                if modo == "values":
                    ultimo = contenido
            if ultimo is None:
                raise RuntimeError("El grafo no devolvió un estado final")
            return ultimo
        return grafo.invoke(estado, config=config_actual)

    try:
        resultado = ejecutar_grafo(config)
    except Exception as error_grafo:
        logger.warning(
            "Fallo en grafo.invoke para sesión %s (%s); reintentando con hilo limpio.",
            request.session_id,
            error_grafo,
        )
        try:
            if respuesta_guardada() or any(item.get("tipo") == "funcion" for item in actividad.actividades):
                raise RuntimeError("No se reintenta una ejecución que ya inició herramientas") from error_grafo
            config_limpio = {
                "configurable": {
                    "thread_id": f"{request.session_id}-recovery-{uuid.uuid4().hex[:8]}",
                    "drive_request_id": drive_request_id,
                },
                "callbacks": [actividad],
            }
            resultado = ejecutar_grafo(config_limpio)
        except Exception as error_final:
            logger.exception("Error definitivo en grafo.invoke: %s", error_final)
            guardada = respuesta_guardada()
            respuesta_error = ChatResponse(
                respuesta=(guardada + "\n\nLa respuesta se interrumpió. Otras acciones solicitadas sin resultado guardado quedan sin confirmar.") if guardada else (
                    "Ocurrió una interrupción temporal al procesar tu solicitud. "
                    "Por favor intenta enviarla nuevamente en unos segundos."
                ),
                actividades=actividad.actividades,
            )
            _guardar_interaccion_en_bd(
                session_id=request.session_id,
                usuario_id=usuario_id,
                mensaje_usuario=request.mensaje,
                respuesta_chat=respuesta_error,
            )
            return respuesta_error

    respuesta = respuesta_guardada() or contenido_a_texto(resultado["messages"][-1])

    archivo_almacen_url = None
    reportes_historicos: list[dict[str, str]] = []
    advertencia_ubicacion: str | None = None
    advertencia_archivos_sueltos: str | None = None
    advertencia_xmls_sin_apoyo: str | None = None
    advertencia_productos_regalo: str | None = None
    resumen_reporte = None
    bloqueado_por_confirmacion = False
    factores_consultados = None
    texto_usuario = request.mensaje.lower()
    pide_reportes = bool(re.search(r"\b(reportes?|excel|xlsx)\b", texto_usuario))
    pide_reciente = bool(re.search(r"\b([uú]ltim[oa]s?|m[aá]s recientes?|recientes?)\b", texto_usuario))
    pide_txt = _solicita_descarga(request.mensaje, "txt")
    pide_excel = _solicita_descarga(request.mensaje, "excel")
    solicita_fecha = bool(re.search(
        r"\b(?:\d{1,4}[-/]\d{1,2}(?:[-/]\d{2,4})?|\d{1,2}\s+de\s+"
        r"(?:enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre))\b",
        texto_usuario,
    ))
    if not pide_txt and re.fullmatch(r"\s*(s[ií]|claro|ok|adelante|comas|tabulaciones|tabs)([ ,.!]*(por favor|comas|tabulaciones|tabs))*[.! ]*", texto_usuario):
        previos = list(resultado["messages"])
        for indice in range(len(previos) - 1, -1, -1):
            if getattr(previos[indice], "type", None) == "human":
                anterior = next((m for m in reversed(previos[:indice]) if getattr(m, "type", None) == "ai" and contenido_a_texto(m)), None)
                pide_txt = bool(anterior and re.search(r"\b(txt|aspel)\b", contenido_a_texto(anterior), re.IGNORECASE) and "?" in contenido_a_texto(anterior))
                break
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
        if datos.get("ok") and datos.get("tipo_consulta") == "catalogo_factores" and isinstance(datos.get("factores_disponibles"), dict) and re.search(r"\bfactores\b", texto_usuario):
            factores_consultados = datos["factores_disponibles"]
        if pide_reportes and datos.get("ok") and datos.get("tipo") == "busqueda_historica" and not reportes_historicos:
            lista_rep = datos.get("reportes", [])
            fecha_solicitada = re.search(r"\b(?:\d{2}[-/]\d{2}[-/]\d{4}|\d{4}[-/]\d{2}[-/]\d{2})\b", request.mensaje)
            if fecha_solicitada:
                fecha_texto = fecha_solicitada.group()
                if re.match(r"^\d{4}/", fecha_texto):
                    fecha_texto = fecha_texto.replace("/", "-")
                try:
                    fecha_normalizada = normalizar_fecha_reporte(fecha_texto)
                except ValueError:
                    fecha_normalizada = None
                lista_rep = [r for r in lista_rep if fecha_normalizada and r.get("fecha") == fecha_normalizada]
            if (
                not datos.get("fecha")
                and lista_rep
                and pide_reciente
            ):
                def fecha_orden(reporte):
                    try:
                        return datetime.strptime(reporte.get("fecha", ""), "%d-%m-%Y")
                    except (ValueError, TypeError):
                        return datetime.min
                fecha_mas_reciente = max(lista_rep, key=fecha_orden).get("fecha")
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
            if resumen_reporte is None:
                resumen_reporte = datos["resumen"]

    if factores_consultados:
        respuesta = _tabla_factores(factores_consultados)
    if reportes_historicos and pide_reciente:
        if re.search(r"\bcarpeta\b", texto_usuario):
            fecha = reportes_historicos[0]["fecha"]
            nombres = "\n".join(f"- **{reporte['nombre']}**" for reporte in reportes_historicos)
            respuesta = f"La carpeta de reportes más reciente es **{fecha}**.\n\nReportes disponibles:\n\n{nombres}\n\nAquí tienes los reportes de esa carpeta por si los necesitas."
        else:
            respuesta += "\n\nAquí tienes los reportes de esa fecha por si los necesitas."

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
        and not re.search(r"(?:sin|no ten[ií]an|no contaban con).{0,50}(?:archivo|txt|pdf|apoyo)", respuesta, re.IGNORECASE | re.DOTALL)
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
        and archivo_almacen_url is None and pide_excel and not reportes_historicos
        and not solicita_fecha
        and (CARPETA_DATOS / NOMBRE_ARCHIVO_BASE).is_file()
    ):
        archivo_almacen_url = "/api/v1/almacen/download"

    # Detectar si el asistente ofrece/menciona el TXT de salida para Aspel (evitando falsos positivos por "TXT de apoyo")
    archivo_txt_url = None
    resp_lower = respuesta.lower()
    if not bloqueado_por_confirmacion and pide_txt:
        if re.search(r"tabulaci[oó]n|tabulaciones|\btabs\b", texto_usuario) and (
            CARPETA_DATOS / NOMBRE_TXT_TABS
        ).is_file():
            archivo_txt_url = "/api/v1/almacen/download/txt?separador=tabs"
        elif (CARPETA_DATOS / NOMBRE_TXT_COMAS).is_file():
            archivo_txt_url = "/api/v1/almacen/download/txt?separador=comas"

    if bloqueado_por_confirmacion:
        archivo_almacen_url = None
        archivo_txt_url = None
        reportes_historicos = []

    if resumen_reporte and not bloqueado_por_confirmacion:
        explicacion = explicar_procedencia_reporte(resumen_reporte)
        if explicacion:
            respuesta = f"{respuesta}\n\n{explicacion}"

    respuesta_final = ChatResponse(
        respuesta=respuesta,
        archivo_almacen_url=archivo_almacen_url,
        archivo_txt_url=archivo_txt_url,
        reportes_historicos=reportes_historicos,
        actividades=actividad.actividades,
    )
    from app.services.contexto_decisiones import contexto
    ctx = contexto.get()
    if ctx and ctx.get("interaccion"):
        respuesta_final.interaccion = ctx["interaccion"]
        respuesta_final.respuesta = "Revisa las opciones y tus decisiones antes de continuar."
    from app.services.revision_reportes import revision_actual
    respuesta_final.revision_reporte = revision_actual(CARPETA_DATOS / NOMBRE_ARCHIVO_BASE, request.session_id, usuario_id)
    if respuesta_final.revision_reporte and respuesta_final.revision_reporte.get("pendientes"):
        respuesta_final.archivo_txt_url = None
        respuesta_final.respuesta += "\n\nLos campos pendientes están señalados en el Excel. Conservé el costo de compra cuando estaba disponible. Completa las líneas y los precios pendientes y adjunta el Excel para validar y generar los TXT."
    from app.services.almacen.avisos import avisos_estado
    respuesta_final.avisos = avisos_estado(respuesta_final.interaccion, respuesta_final.revision_reporte, resumen_reporte)
    _guardar_interaccion_en_bd(
        session_id=request.session_id,
        usuario_id=usuario_id,
        mensaje_usuario=request.mensaje,
        respuesta_chat=respuesta_final,
    )
    return respuesta_final


def _ejecutar_chat(request: ChatRequest, usuario_id: int | None = None) -> ChatResponse:
    from app.services.contexto_decisiones import contexto
    from app.services import decisiones as servicio
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        servicio.verificar_dueno(db, request.session_id, usuario_id)
    ctx = {"session_id": request.session_id, "usuario_id": usuario_id}
    token = contexto.set(ctx)
    try:
        pendiente = servicio.leer(request.session_id, usuario_id)
        if request.decisiones:
            return _continuar_decisiones(request, usuario_id)
        if pendiente and pendiente["interaccion"]["estado"] in {"pendiente", "ejecutando"}:
            envio = servicio.respuesta_textual(pendiente, request.mensaje) if pendiente["interaccion"]["estado"] == "pendiente" else None
            if envio:
                pendiente = servicio.guardar_envio(request.session_id, usuario_id, envio)
            respuesta = ChatResponse(respuesta="Actualicé tu selección. Revisa el resumen y pulsa Aplicar decisiones y continuar." if envio else "Hay decisiones pendientes. Selecciona las opciones de la tarjeta o indica claramente la respuesta que deseas cambiar.", interaccion=pendiente["interaccion"])
            _guardar_interaccion_en_bd(session_id=request.session_id, usuario_id=usuario_id, mensaje_usuario=request.mensaje, respuesta_chat=respuesta)
            return respuesta
        from app.services.revision_reportes import revision_actual
        revision = revision_actual(CARPETA_DATOS / NOMBRE_ARCHIVO_BASE, request.session_id, usuario_id)
        if revision and (revision["pendientes"] or revision.get("relacionados")) and re.search(r"(ya\b.*\b(llen|complet|correg)|\btxt\b)", request.mensaje, re.IGNORECASE):
            respuesta = ChatResponse(respuesta="Adjunta el Excel corregido en la tarjeta y pulsa Validar y generar TXT. Revisaré las líneas introducidas y conservaré los precios que hayas escrito; completaré solo los vacíos con el factor confirmado.", revision_reporte=revision)
            _guardar_interaccion_en_bd(session_id=request.session_id, usuario_id=usuario_id, mensaje_usuario=request.mensaje, respuesta_chat=respuesta)
            return respuesta
        return _ejecutar_chat_impl(request, usuario_id)
    finally:
        contexto.reset(token)


def _continuar_decisiones(request, uid):
    from app.services import decisiones as servicio
    from app.services.contexto_decisiones import contexto
    from app.agents.tools import HERRAMIENTAS
    from app.services.revision_reportes import revision_actual
    actividad = ActividadHandler(getattr(_CONTEXTO_JOB, "job_id", None))
    estado = servicio.guardar_envio(request.session_id, uid, request.decisiones)
    i = estado["interaccion"]
    if request.decisiones.accion == "borrador":
        return ChatResponse(respuesta="Borrador guardado.", interaccion=i)
    if request.decisiones.accion == "cancelar":
        respuesta = ChatResponse(respuesta="Operación cancelada.", interaccion=i)
    else:
        try:
            args, cancelar = servicio.traducir(estado)
            if cancelar:
                i["estado"] = "cancelada"
                with SessionLocal() as db:
                    from app.models.conversacion import ConfirmacionPendiente
                    fila = db.scalar(select(ConfirmacionPendiente).where(ConfirmacionPendiente.conversacion_id == request.session_id))
                    fila.datos_json = json.dumps(estado, ensure_ascii=False)
                    db.commit()
                respuesta = ChatResponse(respuesta="Operación cancelada; no se ejecutaron las decisiones.", interaccion=i)
            else:
                contexto.get()["continuacion"] = args
                if estado["herramienta"] == "revisar_reporte_almacen":
                    from app.services.revision_reportes import reanudar_revision
                    revision = reanudar_revision(args["reporte_id"], args["version"], args.get("factores_elegidos", {}), uid)
                    resultado = {"ok": True, "mensaje": revision["resumen_revision"], "revision_reporte": revision}
                else:
                    herramienta = next(h for h in HERRAMIENTAS if h.name == estado["herramienta"])
                    resultado = servicio.revalidar_aprobacion(estado, args)
                    if resultado is None:
                        resultado = json.loads(herramienta.invoke(args, config={"callbacks": [actividad]}))
                fallo = resultado.get("ok") is False and not resultado.get("requiere_confirmacion")
                servicio.finalizar(request.session_id, uid, estado, resultado, error=fallo)
                siguiente = None
                if resultado.get("requiere_confirmacion"):
                    anteriores = [*i.get("anteriores", []), {k: deepcopy(v) for k, v in i.items() if k != "anteriores"}]
                    siguiente = servicio.registrar(request.session_id, uid, resultado, herramienta.name, contexto.get().get("continuacion", args), anteriores)
                revision = resultado.get("revision_reporte") or revision_actual(CARPETA_DATOS / NOMBRE_ARCHIVO_BASE, request.session_id, uid)
                reporte = resultado.get("reporte_generado") is True
                texto = "Revisa las siguientes decisiones para continuar." if siguiente else resultado.get("mensaje") or ("Las decisiones se aplicaron y el reporte está listo." if reporte else "Las decisiones se aplicaron." if not fallo else resultado.get("error", "No se pudo completar la operación."))
                if reporte:
                    resumen = resultado.get("resumen", {})
                    total = resumen.get("productos_acumulados", resumen.get("total_productos_acumulados", resumen.get("total_productos")))
                    if total is not None:
                        texto += f" El reporte contiene {total} productos."
                    fecha = resumen.get("fecha_reporte_base") or args.get("carpeta_especifica")
                    if fecha:
                        texto += f" La carpeta procesada es {fecha}."
                    elecciones = []
                    for pregunta in i.get("preguntas", []):
                        seleccion = i.get("respuestas", {}).get(pregunta["id"], {})
                        opcion = next((o for o in pregunta.get("opciones", []) if o["id"] == seleccion.get("opcion")), None)
                        if opcion:
                            elecciones.append(f"- {pregunta['titulo']} {opcion['titulo']}")
                    if elecciones:
                        texto += "\n\nDecisiones aplicadas\n" + "\n".join(elecciones)
                    explicacion = explicar_procedencia_reporte(resumen)
                    if explicacion:
                        texto += "\n\n" + explicacion
                avisos = [resultado.get(k) for k in ("advertencia_ubicacion", "advertencia_xmls_sin_apoyo", "advertencia_productos_regalo") if isinstance(resultado.get(k), str)]
                if avisos:
                    texto += "\n\n" + "\n\n".join(avisos)
                from app.services.almacen.avisos import avisos_estado
                avisos_estructurados = avisos_estado(siguiente or i, revision, resultado.get("resumen"))
                if revision and revision.get("pendientes"):
                    texto += "\n\nLos campos pendientes están señalados en el Excel. Conservé el costo de compra cuando estaba disponible. Completa las líneas y los precios pendientes y adjunta el Excel para validar y generar los TXT."
                respuesta = ChatResponse(respuesta=texto, interaccion=siguiente or i, revision_reporte=revision, avisos=avisos_estructurados,
                    actividades=actividad.actividades,
                    archivo_almacen_url="/api/v1/almacen/download" if reporte else None,
                    archivo_txt_url="/api/v1/almacen/download/txt" if reporte and not (revision and revision.get("pendientes")) else None)
        except Exception:
            servicio.finalizar(request.session_id, uid, estado, {}, error=True)
            respuesta = ChatResponse(respuesta="La operación se interrumpió. Revisa su resultado antes de iniciar otra; no se repetirá automáticamente.", interaccion=i, actividades=actividad.actividades)
            logger.exception("Error al aplicar decisiones %s", i["id"])
    # La continuación directa también debe quedar en la memoria del grafo.
    config = {"configurable": {"thread_id": request.session_id}}
    if callable(getattr(grafo, "update_state", None)) and _memoria_grafo_tiene_mensajes(config):
        try:
            grafo.update_state(config, {"messages": [HumanMessage(content=request.mensaje), AIMessage(content=respuesta.respuesta)]}, as_node="flucito")
        except Exception:
            logger.warning("No se pudo actualizar la memoria del grafo tras confirmar decisiones", exc_info=True)
    _guardar_interaccion_en_bd(session_id=request.session_id, usuario_id=uid, mensaje_usuario=request.mensaje, respuesta_chat=respuesta)
    return respuesta


@router.put("/chat/conversaciones/{session_id}/decisiones")
def guardar_borrador_decisiones(session_id: str, envio: EnvioDecisiones, usuario_actual: Usuario | None = Depends(obtener_usuario_opcional)):
    from app.services.decisiones import guardar_envio
    if envio.accion != "borrador":
        raise HTTPException(422, "Este endpoint solo guarda borradores.")
    return guardar_envio(session_id, getattr(usuario_actual, "id", None), envio)["interaccion"]


def _trabajador_chat(job_id: str, request: ChatRequest, usuario_id: int | None = None) -> None:
    try:
        _CONTEXTO_JOB.job_id = job_id
        if usuario_id is None:
            respuesta = _ejecutar_chat(request)
        else:
            respuesta = _ejecutar_chat(request, usuario_id=usuario_id)
        with _JOBS_LOCK:
            if job_id in _JOBS:
                _JOBS[job_id]["status"] = "completed"
                _JOBS[job_id]["result"] = respuesta
                _JOBS[job_id]["texto_provisional"] = respuesta.respuesta
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
            "etapa": "pensando",
            "actividades": [],
            "texto_provisional": "",
            "usuario_id": uid,
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
    with _JOBS_LOCK:
        job = _JOBS.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Tarea de chat no encontrada")
        uid = getattr(usuario_actual, "id", None)
        if job.get("usuario_id") is not None and job["usuario_id"] != uid:
            raise HTTPException(status_code=403, detail="No tienes acceso a esta tarea")
        return ChatJobStatusResponse(
            job_id=job_id,
            status=job["status"],
            result=job["result"],
            error=job["error"],
            etapa=job.get("etapa", "pensando"),
            actividades=job.get("actividades", []),
            texto_provisional=job.get("texto_provisional", ""),
        )


@router.get("/chat/events/{job_id}")
def eventos_chat(job_id: str, usuario_actual: Usuario | None = Depends(obtener_usuario_opcional)):
    # Validar antes de enviar las cabeceras del stream.
    consultar_estado_chat(job_id, usuario_actual)

    async def eventos():
        anterior = None
        latido = time.monotonic()
        while True:
            try:
                estado = consultar_estado_chat(job_id, usuario_actual)
            except HTTPException:
                return
            actual = estado.model_dump_json()
            if actual != anterior:
                yield f"data: {actual}\n\n"
                anterior = actual
            if estado.status in ("completed", "failed"):
                return
            if time.monotonic() - latido >= 10:
                yield ": keepalive\n\n"
                latido = time.monotonic()
            await asyncio.sleep(0.15)

    return StreamingResponse(eventos(), media_type="text/event-stream", headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"})


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
    from app.services.decisiones import leer
    decision_actual = leer(session_id, usuario_actual.id)
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
                avisos=meta.get("avisos") or [],
                interaccion=(decision_actual["interaccion"] if decision_actual and (meta.get("interaccion") or {}).get("id") == decision_actual["interaccion"]["id"] else meta.get("interaccion")),
                revision_reporte=meta.get("revision_reporte"),
                archivo_almacen_url=meta.get("archivo_almacen_url"),
                archivo_txt_url=meta.get("archivo_txt_url"),
                reportes_historicos=meta.get("reportes_historicos") or [],
                actividades=meta.get("actividades") or [],
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
