from langchain_core.messages import SystemMessage
from langchain_groq import ChatGroq
from langgraph.graph import END, StateGraph

from app.agents.prompts import SYSTEM_PROMPT
from app.agents.state import AsistenteState
from app.core.config import settings

llm = ChatGroq(
    model=settings.groq_model,
    api_key=settings.groq_api_key,
    temperature=0.4,
)


def nodo_flucito(state: AsistenteState) -> AsistenteState:
    """Nodo de conversación principal. Se encarga temporalmente de todo; después será el nodo
    de 'charla general', con nodos hermanos que se usaran para tareas especificas.
    """
    mensajes = [SystemMessage(content=SYSTEM_PROMPT)] + state["messages"]
    respuesta = llm.invoke(mensajes)
    return {"messages": [respuesta]}

graph_builder = StateGraph(AsistenteState)
graph_builder.add_node("flucito", nodo_flucito)
graph_builder.set_entry_point("flucito")
graph_builder.add_edge("flucito", END)

grafo = graph_builder.compile()