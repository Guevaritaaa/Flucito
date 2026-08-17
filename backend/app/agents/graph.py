import logging

from langchain_core.messages import SystemMessage
from langgraph.graph import END, StateGraph
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import ToolNode

from app.agents.prompts import SYSTEM_PROMPT
from app.agents.state import AsistenteState
from app.agents.tools import generar_entradas_almacen
from app.agents.llm_router import crear_llms


logger = logging.getLogger(__name__)


HERRAMIENTAS = [generar_entradas_almacen]

llm_primario, llm_respaldo = crear_llms()
llm_primario_con_herramientas = llm_primario.bind_tools(HERRAMIENTAS)
llm_respaldo_con_herramientas = (
    llm_respaldo.bind_tools(HERRAMIENTAS) if llm_respaldo else None
)


def es_error_reintentable(error: Exception) -> bool:
    """Identifica fallas temporales o de disponibilidad del proveedor."""
    status_code = getattr(error, "status_code", None)
    response = getattr(error, "response", None)
    status_code = status_code or getattr(response, "status_code", None)

    if status_code in {404, 408, 429, 500, 502, 503, 504}:
        return True

    mensaje = str(error).lower()
    return any(
        texto in mensaje
        for texto in ("timeout", "timed out", "model_not_found", "temporarily")
    )


def invocar_con_fallback(mensajes: list, primario, respaldo):
    """Invoca el primario y cambia al respaldo solo ante errores recuperables."""
    try:
        return primario.invoke(mensajes)
    except Exception as error:
        if respaldo is None or not es_error_reintentable(error):
            raise

        logger.warning("Proveedor primario no disponible; usando fallback: %s", error)
        return respaldo.invoke(mensajes)


def nodo_flucito(state: AsistenteState) -> AsistenteState:
    """Nodo principal de Flucito."""
    mensajes = [SystemMessage(content=SYSTEM_PROMPT)] + state["messages"]
    respuesta = invocar_con_fallback(
        mensajes,
        llm_primario_con_herramientas,
        llm_respaldo_con_herramientas,
    )
    return {"messages": [respuesta]}


def siguiente_nodo(state: AsistenteState) -> str:
    """Envía la ejecución a herramientas solo cuando el modelo las solicita."""
    ultima_respuesta = state["messages"][-1]
    if getattr(ultima_respuesta, "tool_calls", None):
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
