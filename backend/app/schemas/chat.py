from pydantic import BaseModel


class ChatRequest(BaseModel):
    mensaje: str


class ChatResponse(BaseModel):
    respuesta: str