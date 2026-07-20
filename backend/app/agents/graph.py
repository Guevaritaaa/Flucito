from langchain_core.messages import SystemMessage
from langchain_groq import ChatGroq
from langgraph.graph import END, StateGraph
from langgraph.checkpoint.memory import MemorySaver

from app.agents.prompts import SYSTEM_PROMPT
from app.agents.state import AsistenteState
from app.core.config import settings

llm = ChatGroq(
    model=settings.groq_model,
    api_key=settings.groq_api_key,
    temperature=0.4,
)


def nodo_flucito(state: AsistenteState) -> AsistenteState:
    """Nodo Principal de Flucito, recibe los mensajes del usuario y retorna la respuesta del LLM."""
    mensajes = [SystemMessage(content=SYSTEM_PROMPT)] + state["messages"]
    respuesta = llm.invoke(mensajes)
    return {"messages": [respuesta]}

graph_builder = StateGraph(AsistenteState)
graph_builder.add_node("flucito", nodo_flucito)
graph_builder.set_entry_point("flucito")
graph_builder.add_edge("flucito", END)

memoria = MemorySaver()
grafo = graph_builder.compile(checkpointer=memoria)