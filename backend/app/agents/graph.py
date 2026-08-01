from langchain_core.messages import SystemMessage
from langchain_groq import ChatGroq
from langgraph.graph import END, StateGraph
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import ToolNode

from app.agents.prompts import SYSTEM_PROMPT
from app.agents.state import AsistenteState
from app.agents.tools import generar_reporte_cfdi_job
from app.core.config import settings


HERRAMIENTAS = [generar_reporte_cfdi_job]

llm = ChatGroq(
    model=settings.groq_model,
    api_key=settings.groq_api_key,
    temperature=0.4,
)
llm_con_herramientas = llm.bind_tools(HERRAMIENTAS)


def nodo_flucito(state: AsistenteState) -> AsistenteState:
    """Nodo Principal de Flucito, recibe los mensajes del usuario y retorna la respuesta del LLM."""
    mensajes = [SystemMessage(content=SYSTEM_PROMPT)] + state["messages"]
    job_id = state.get("cfdi_job_id")
    if job_id:
        mensajes.insert(
            1,
            SystemMessage(
                content=(
                    "Hay un job CFDI disponible para esta sesiÃ³n. "
                    f"Si el usuario solicita generar el reporte, llama "
                    f"generar_reporte_cfdi_job con job_id='{job_id}'. "
                    "No inventes otro job_id ni rutas de archivos."
                )
            ),
        )
    respuesta = llm_con_herramientas.invoke(mensajes)
    return {"messages": [respuesta]}
def siguiente_nodo(state: AsistenteState) -> str:
    """Envía la ejecución a las herramientas solo cuando el modelo las solicita."""
    ultima_respuesta = state["messages"][-1]
    if getattr(ultima_respuesta, "tool_calls", None):
        return "herramientas"
    return END


herramientas = ToolNode(HERRAMIENTAS)
graph_builder = StateGraph(AsistenteState)
graph_builder.add_node("flucito", nodo_flucito)  # Add node for flucito
graph_builder.add_node("herramientas", herramientas)
graph_builder.set_entry_point("flucito")
graph_builder.add_conditional_edges("flucito", siguiente_nodo)
graph_builder.add_edge("herramientas", "flucito")

memoria = MemorySaver()
grafo = graph_builder.compile(checkpointer=memoria)
