"""Construcción centralizada de los modelos usados por Flucito."""

import json
import logging
import math
import time
import uuid

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, convert_to_messages, messages_to_dict
from langchain_groq import ChatGroq
from langchain_openai import ChatOpenAI

from app.core.config import settings

logger = logging.getLogger(__name__)


class PresupuestoGroqError(ValueError):
    """No fue posible autorizar el envío de la carga a Groq."""


def crear_llm_groq(timeout: float | None = None) -> BaseChatModel:
    """Crea el modelo de Groq sin reintentos ocultos del SDK."""
    return ChatGroq(
        model=settings.groq_model,
        api_key=settings.groq_api_key,
        temperature=0.1,
        max_tokens=settings.groq_max_output_tokens,
        max_retries=0,
        timeout=timeout,
    )


def crear_llm_openai(modelo: str | None = None, responses: bool | None = None) -> BaseChatModel:
    """Crea el modelo elegido, con resúmenes públicos opcionales en Responses."""
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY no está configurada")

    usar_responses = settings.openai_use_responses_api if responses is None else responses
    opciones = {}
    if usar_responses:
        opciones["reasoning"] = {"effort": settings.openai_reasoning_effort}
        if settings.openai_reasoning_summary:
            opciones["reasoning"]["summary"] = "auto"
        if settings.openai_reasoning_effort != "none":
            opciones["include"] = ["reasoning.encrypted_content"]
    else:
        opciones.update(reasoning_effort="none", temperature=0.1)
    return ChatOpenAI(
        model=modelo or settings.openai_model,
        api_key=settings.openai_api_key,
        **opciones,
        max_retries=0,
        use_responses_api=usar_responses,
        output_version="responses/v1" if usar_responses else "v0",
        use_previous_response_id=False,
        store=False,
    )


def crear_llms() -> tuple[BaseChatModel, BaseChatModel | None]:
    """Devuelve modelo primario y fallback sin ejecutar llamadas externas."""
    if settings.llm_primary_provider.lower() == "openai":
        primario = crear_llm_openai()
        respaldo = (
            crear_llm_groq()
            if settings.llm_fallback_enabled and settings.groq_api_key
            else None
        )
    else:
        primario = crear_llm_groq()
        respaldo = (
            crear_llm_openai()
            if settings.llm_fallback_enabled and settings.openai_api_key
            else None
        )

    return primario, respaldo


def obtener_estado_http(error: Exception) -> int | None:
    return getattr(error, "status_code", None) or getattr(
        getattr(error, "response", None), "status_code", None
    )


def es_error_reintentable(error: Exception) -> bool:
    """Un 413 nunca habilita el reenvío de la misma carga."""
    if isinstance(error, ValueError) or obtener_estado_http(error) == 413:
        return False
    estado = obtener_estado_http(error)
    if estado in {401, 403}:
        return False
    if estado in {400, 404, 408, 429, 500, 502, 503, 504}:
        return True
    return any(texto in str(error).lower() for texto in (
        "timeout", "timed out", "model_not_found", "temporarily",
        "tool_use_failed", "failed_generation", "tool call", "rate_limit",
        "rate limit", "connection", "bad request",
    ))


def estimar_tokens_carga(mensajes: list, modelo) -> int:
    """Estimación local conservadora: JSON completo a 3 bytes/token + envoltura.

    Incluye sistema, historial, argumentos/resultados de tools y los esquemas
    realmente enlazados. No descarga tokenizadores ni envía datos a un proveedor.
    """
    carga = {
        "messages": messages_to_dict(convert_to_messages(mensajes)),
        "options": getattr(modelo, "kwargs", {}),
    }
    serializado = json.dumps(carga, ensure_ascii=False)
    return math.ceil(len(serializado.encode("utf-8")) / 3) + 12 * len(mensajes)


def preparar_mensajes(mensajes, proveedor, modelo):
    base = getattr(modelo, "bound", modelo)
    if proveedor == "openai" and getattr(base, "use_responses_api", False):
        return mensajes
    return [m.model_copy(update={"content": str(m.text), "additional_kwargs": {}})
            if isinstance(m, AIMessage) and isinstance(m.content, list) else m for m in mensajes]


def invocar_con_fallback(mensajes: list, primario, respaldo):
    """Registra cada intento y condiciona cualquier envío a Groq al presupuesto."""
    request_id = uuid.uuid4().hex
    proveedor = settings.llm_primary_provider
    alternativo = "groq" if proveedor == "openai" else "openai"

    def registrar(modelo, proveedor, inicio, resultado, motivo=None, estimados=None, estado=None):
        base = getattr(modelo, "bound", modelo)
        evento = {
            "event": "llm_call", "request_id": request_id,
            "provider": proveedor,
            "model": getattr(base, "model_name", None) or (
                settings.openai_model if proveedor == "openai" else settings.groq_model
            ),
            "duration_ms": round((time.perf_counter() - inicio) * 1000, 2),
            "result": resultado, "fallback_reason": motivo,
            "estimated_tokens": estimados, "status_code": estado,
            "api": "responses" if getattr(base, "use_responses_api", False) else "chat_completions",
        }
        logger.info(json.dumps(evento))

    def intentar(modelo, proveedor, motivo=None):
        inicio = time.perf_counter()
        estimados = None
        carga = preparar_mensajes(mensajes, proveedor, modelo)
        if proveedor == "groq":
            try:
                estimados = estimar_tokens_carga(carga, modelo) + settings.groq_max_output_tokens
            except (TypeError, ValueError):
                registrar(modelo, proveedor, inicio, "skipped", "token_estimation_failed")
                raise PresupuestoGroqError("No se pudo estimar la carga para Groq") from None
            if estimados > settings.groq_tpm_budget:
                registrar(modelo, proveedor, inicio, "skipped", "groq_token_budget_exceeded", estimados)
                raise PresupuestoGroqError("La carga estimada supera el presupuesto de Groq")
        try:
            respuesta = modelo.invoke(carga)
        except Exception as error:
            registrar(modelo, proveedor, inicio, "error", motivo, estimados, obtener_estado_http(error))
            raise
        registrar(modelo, proveedor, inicio, "success", motivo, estimados)
        return respuesta

    try:
        return intentar(primario, proveedor)
    except Exception as error:
        estado = obtener_estado_http(error)
        motivo = f"primary_http_{estado}" if estado else "primary_recoverable_error"
        if not es_error_reintentable(error):
            if estado == 413:
                registrar(primario, proveedor, time.perf_counter(), "retry_skipped", "http_413_payload_rejected", estado=estado)
            raise
        if respaldo is not None:
            try:
                return intentar(respaldo, alternativo, motivo)
            except PresupuestoGroqError:
                # Conserva el error original si no fue posible enviar al respaldo.
                raise error from None
        # Un solo reintento explícito si no hay proveedor alternativo.
        return intentar(primario, proveedor, "fallback_unavailable_retry_primary")
