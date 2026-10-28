import logging

from langchain_core.messages import SystemMessage, ToolMessage
from langgraph.graph import END, StateGraph
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import ToolNode

from app.agents.prompts import SYSTEM_PROMPT
from app.agents.state import AsistenteState
from app.agents.tools import HERRAMIENTAS
from app.agents.llm_router import crear_llms


logger = logging.getLogger(__name__)

MAX_ITERACIONES_TOOLS = 4

llm_primario, llm_respaldo = crear_llms()
llm_primario_con_herramientas = llm_primario.bind_tools(HERRAMIENTAS)
llm_respaldo_con_herramientas = (
    llm_respaldo.bind_tools(HERRAMIENTAS) if llm_respaldo else None
)


def es_error_reintentable(error: Exception) -> bool:
    """Identifica fallas temporales o de disponibilidad del proveedor."""
    if isinstance(error, ValueError):
        return False

    status_code = getattr(error, "status_code", None)
    response = getattr(error, "response", None)
    status_code = status_code or getattr(response, "status_code", None)

    if status_code in {400, 404, 408, 413, 429, 500, 502, 503, 504}:
        return True

    mensaje = str(error).lower()
    return any(
        texto in mensaje
        for texto in (
            "timeout",
            "timed out",
            "model_not_found",
            "temporarily",
            "tool_use_failed",
            "failed_generation",
            "tool call",
            "rate_limit",
            "rate limit",
            "connection",
            "bad request",
        )
    )


def invocar_con_fallback(mensajes: list, primario, respaldo):
    """Invoca el primario y cambia al respaldo solo ante errores recuperables."""
    try:
        return primario.invoke(mensajes)
    except Exception as error:
        if not es_error_reintentable(error):
            raise

        if respaldo is not None:
            logger.warning("Proveedor primario no disponible; usando fallback: %s", error)
            return respaldo.invoke(mensajes)

        logger.warning("Error transitorio en proveedor primario sin respaldo; reintentando: %s", error)
        return primario.invoke(mensajes)


def contar_rondas_herramientas_turno_actual(mensajes: list) -> int:
    """Cuenta cuántas rondas de llamada a herramientas se han ejecutado desde el último mensaje del usuario."""
    rondas = 0
    for mensaje in reversed(mensajes):
        tipo = getattr(mensaje, "type", None)
        if tipo == "human":
            break
        if tipo == "ai" and getattr(mensaje, "tool_calls", None):
            rondas += 1
    return rondas


MAX_TURNOS_HISTORIAL_LLM = 5
MAX_CARACTERES_TOOL_TURNO_ANTERIOR = 900


def compactar_historial_para_llm(mensajes: list) -> list:
    """Recorta salidas extensas de herramientas de turnos anteriores para no exceder el límite TPM de Groq."""
    if not mensajes:
        return []

    indices_humanos = [
        idx
        for idx, msg in enumerate(mensajes)
        if getattr(msg, "type", None) == "human"
    ]
    if not indices_humanos:
        return list(mensajes)

    inicio = (
        indices_humanos[-MAX_TURNOS_HISTORIAL_LLM]
        if len(indices_humanos) > MAX_TURNOS_HISTORIAL_LLM
        else 0
    )
    idx_turno_actual = indices_humanos[-1]

    compactados: list = []
    for idx in range(inicio, len(mensajes)):
        msg = mensajes[idx]
        if (
            idx < idx_turno_actual
            and getattr(msg, "type", None) == "tool"
            and isinstance(getattr(msg, "content", None), str)
            and len(msg.content) > MAX_CARACTERES_TOOL_TURNO_ANTERIOR
        ):
            contenido_corto = (
                msg.content[:MAX_CARACTERES_TOOL_TURNO_ANTERIOR]
                + "... [salida resumida de turno anterior]"
            )
            compactados.append(
                ToolMessage(
                    content=contenido_corto,
                    tool_call_id=getattr(msg, "tool_call_id", ""),
                    name=getattr(msg, "name", None),
                )
            )
        else:
            compactados.append(msg)

    return compactados


def nodo_flucito(state: AsistenteState) -> AsistenteState:
    """Nodo principal de Flucito con límite de rondas de herramientas por turno."""
    rondas_actuales = contar_rondas_herramientas_turno_actual(state["messages"])
    historial_compacto = compactar_historial_para_llm(state["messages"])

    if rondas_actuales >= MAX_ITERACIONES_TOOLS:
        logger.warning(
            "Se alcanzó el límite de %d rondas de herramientas en este turno; sintetizando respuesta final.",
            MAX_ITERACIONES_TOOLS,
        )
        prompt_cierre = (
            f"{SYSTEM_PROMPT}\n\n"
            "NOTA DEL SISTEMA: Ya alcanzaste el límite máximo de llamadas a herramientas para este mensaje. "
            "Responde ahora directamente al usuario resumiendo la información que ya obtuviste."
        )
        mensajes = [SystemMessage(content=prompt_cierre)] + historial_compacto
        respuesta = invocar_con_fallback(
            mensajes,
            llm_primario,
            llm_respaldo,
        )
        return {"messages": [respuesta]}

    mensajes = [SystemMessage(content=SYSTEM_PROMPT)] + historial_compacto
    respuesta = invocar_con_fallback(
        mensajes,
        llm_primario_con_herramientas,
        llm_respaldo_con_herramientas,
    )
    return {"messages": [respuesta]}


def siguiente_nodo(state: AsistenteState) -> str:
    """Envía la ejecución a herramientas solo cuando el modelo las solicita y no excede el límite."""
    ultima_respuesta = state["messages"][-1]
    if getattr(ultima_respuesta, "tool_calls", None):
        rondas = contar_rondas_herramientas_turno_actual(state["messages"])
        if rondas > MAX_ITERACIONES_TOOLS:
            return END
        return "herramientas"
    return END


herramientas = ToolNode(HERRAMIENTAS)
graph_builder = StateGraph(AsistenteState)
graph_builder.add_node("flucito", nodo_flucito)
graph_builder.add_node("herramientas", herramientas)
graph_builder.set_entry_point("flucito")
graph_builder.add_conditional_edges("flucito", siguiente_nodo)
graph_builder.add_edge("herramientas", "flucito")

memoria = MemorySaver()
grafo = graph_builder.compile(checkpointer=memoria)
