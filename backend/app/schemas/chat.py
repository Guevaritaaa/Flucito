from pydantic import BaseModel


class ChatRequest(BaseModel):
    mensaje: str
    session_id: str


class ChatResponse(BaseModel):
    respuesta: str
    archivo_almacen_url: str | None = None
