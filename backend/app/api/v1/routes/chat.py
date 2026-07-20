
from fastapi import APIRouter

from app.agents.graph import grafo
from app.schemas.chat import ChatRequest, ChatResponse
from langchain_core.messages import HumanMessage

router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    estado = {"messages": [HumanMessage(content=request.mensaje)]}
    config = {"configurable": {"thread_id": request.session_id}}
    resultado = grafo.invoke(estado, config=config)
    respuesta = resultado["messages"][-1].content
    return ChatResponse(respuesta=respuesta)