import logging
import re
import json

from langchain_core.messages import AIMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, StateGraph
from langgraph.checkpoint.memory import MemorySaver

from app.agents.prompts import SYSTEM_PROMPT
from app.agents.state import AsistenteState
from app.agents.tools import HERRAMIENTAS
from app.agents.llm_router import crear_llms, es_error_reintentable, invocar_con_fallback
from app.agents.ejecucion_tools import ejecutar_herramientas
from app.agents.seleccion_tools import enlazar_herramientas, seleccionar_herramientas
from app.core.config import settings


logger = logging.getLogger(__name__)

MAX_ITERACIONES_TOOLS = 4

llm_primario, llm_respaldo = crear_llms()
llm_primario_con_herramientas = enlazar_herramientas(llm_primario, HERRAMIENTAS)
llm_respaldo_con_herramientas = enlazar_herramientas(llm_respaldo, HERRAMIENTAS)


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


def nodo_flucito(state: AsistenteState, config: RunnableConfig = None) -> AsistenteState:
    """Nodo principal de Flucito con límite de rondas de herramientas por turno."""
    rondas_actuales = contar_rondas_herramientas_turno_actual(state["messages"])
    historial_compacto = compactar_historial_para_llm(state["messages"])

    if rondas_actuales >= MAX_ITERACIONES_TOOLS:
        from app.services.almacen.fuentes.operaciones_drive import recuperar
        solicitud = (config or {}).get("configurable", {}).get("drive_request_id")
        guardado = recuperar(solicitud) if solicitud else ""
        if guardado:
            return {"messages": [AIMessage(content=guardado)]}
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
    seleccion = seleccionar_herramientas(state["messages"], HERRAMIENTAS) if settings.llm_reduce_tools_enabled else HERRAMIENTAS
    primario = llm_primario_con_herramientas if seleccion is HERRAMIENTAS else enlazar_herramientas(llm_primario, seleccion)
    respaldo = llm_respaldo_con_herramientas if seleccion is HERRAMIENTAS else enlazar_herramientas(llm_respaldo, seleccion)
    respuesta = invocar_con_fallback(
        mensajes,
        primario,
        respaldo,
    )
    if getattr(respuesta, "invalid_tool_calls", None):
        raise ValueError("El modelo devolvió argumentos de herramienta inválidos; no se ejecutaron")
    # Una pregunta general de carpetas no debe limitarse a la raíz por una
    # elección accidental del modelo. Las ubicaciones explícitas se respetan.
    humanos = [m.content for m in state["messages"] if getattr(m, "type", None) == "human" and isinstance(m.content, str)]
    consulta = humanos[-1] if humanos else ""
    if re.fullmatch(r"\s*(?:verifica|revisa|comprueba)(?:\s+de nuevo|\s+otra vez)?[.!?¿ ]*", consulta, re.IGNORECASE) and len(humanos) > 1:
        consulta = humanos[-2]
    general = bool(re.search(r"\bcarpetas?\b", consulta, re.IGNORECASE)) and not re.search(r"ra[ií]z|documentos entrada|entradas al inventario|reportes?|hist[oó]ric|\d{2}[-/]\d{2}", consulta, re.IGNORECASE)
    if general and getattr(respuesta, "tool_calls", None):
        llamadas = []
        for llamada in respuesta.tool_calls:
            llamada = dict(llamada)
            args = dict(llamada.get("args", {}))
            if llamada.get("name") == "consultar_drive" and args.get("modo_consulta", "explorar_estructura") == "explorar_estructura" and args.get("ubicacion") == "raiz" and not args.get("carpeta_o_fecha"):
                args["ubicacion"] = "todas"
                llamada["args"] = args
            llamadas.append(llamada)
        contenido = respuesta.content
        if isinstance(contenido, list):
            por_id = {c["id"]: c for c in llamadas}
            contenido = [
                {**b, "arguments": json.dumps(por_id[b["call_id"]]["args"], ensure_ascii=False)}
                if isinstance(b, dict) and b.get("type") == "function_call" and b.get("call_id") in por_id else b
                for b in contenido
            ]
        respuesta = respuesta.model_copy(update={"tool_calls": llamadas, "content": contenido})
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


def herramientas(state: AsistenteState, config: RunnableConfig) -> AsistenteState:
    seleccion = seleccionar_herramientas(state["messages"][:-1], HERRAMIENTAS) if settings.llm_reduce_tools_enabled else HERRAMIENTAS
    return ejecutar_herramientas(state, seleccion, config)
graph_builder = StateGraph(AsistenteState)
graph_builder.add_node("flucito", nodo_flucito)
graph_builder.add_node("herramientas", herramientas)
graph_builder.set_entry_point("flucito")
graph_builder.add_conditional_edges("flucito", siguiente_nodo)
graph_builder.add_edge("herramientas", "flucito")

memoria = MemorySaver()
grafo = graph_builder.compile(checkpointer=memoria)
