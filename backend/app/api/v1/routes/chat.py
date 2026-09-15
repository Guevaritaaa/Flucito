import json

from fastapi import APIRouter
from langchain_core.messages import HumanMessage

from app.agents.graph import grafo
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.almacen.excel import CARPETA_DATOS, NOMBRE_ARCHIVO_BASE
from app.services.almacen.txt_aspel import NOMBRE_TXT_COMAS, NOMBRE_TXT_TABS


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

    # Si la base física existe y el asistente la menciona o el usuario la pidió
    if archivo_almacen_url is None and (CARPETA_DATOS / NOMBRE_ARCHIVO_BASE).is_file():
        palabras_clave = ("descarg", "botón", "boton", "archivo excel", "plataforma", "portal")
        if any(p in respuesta.lower() for p in palabras_clave):
            archivo_almacen_url = "/api/v1/almacen/download"

    # Detectar si el asistente ofrece/menciona TXT y agregar URLs de descarga
    archivo_txt_url = None
    resp_lower = respuesta.lower()
    txt_detectado = any(p in resp_lower for p in ("txt", "tabulacion", "comas", "aspel"))
    if txt_detectado:
        if "tabulacion" in resp_lower and (CARPETA_DATOS / NOMBRE_TXT_TABS).is_file():
            archivo_txt_url = "/api/v1/almacen/download/txt?separador=tabs"
        elif (CARPETA_DATOS / NOMBRE_TXT_COMAS).is_file():
            archivo_txt_url = "/api/v1/almacen/download/txt?separador=comas"

    return ChatResponse(
        respuesta=respuesta,
        archivo_almacen_url=archivo_almacen_url,
        archivo_txt_url=archivo_txt_url,
    )
