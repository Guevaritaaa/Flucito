import json

from fastapi import APIRouter
from langchain_core.messages import HumanMessage

from app.agents.graph import grafo
from app.schemas.chat import ChatRequest, ChatResponse


router = APIRouter()


def contenido_a_texto(mensaje) -> str:
    """Normaliza respuestas string y bloques de Responses API."""
    texto = getattr(mensaje, "text", None)
    if isinstance(texto, str):
        return texto

    contenido = getattr(mensaje, "content", "")
    return contenido if isinstance(contenido, str) else str(contenido)


@router.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    """Procesa conversación del asistente y devuelve enlace de almacén."""
    estado = {"messages": [HumanMessage(content=request.mensaje)]}
    config = {"configurable": {"thread_id": request.session_id}}
    resultado = grafo.invoke(estado, config=config)
    respuesta = contenido_a_texto(resultado["messages"][-1])

    archivo_almacen_url = None
    for mensaje in reversed(resultado["messages"]):
        if getattr(mensaje, "type", None) != "tool":
            continue
        try:
            datos = json.loads(mensaje.content)
        except (TypeError, json.JSONDecodeError):
            continue
        if datos.get("ok") and datos.get("reporte_generado") and datos.get("resumen"):
            archivo_almacen_url = "/api/v1/almacen/download"
            break

    return ChatResponse(
        respuesta=respuesta,
        archivo_almacen_url=archivo_almacen_url,
    )
