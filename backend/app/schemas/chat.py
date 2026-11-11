from datetime import datetime
from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    mensaje: str
    session_id: str


class ChatResponse(BaseModel):
    respuesta: str
    archivo_almacen_url: str | None = None
    archivo_txt_url: str | None = None
    reportes_historicos: list[dict[str, str]] = Field(default_factory=list)


class ChatJobCreateResponse(BaseModel):
    job_id: str
    status: str


class ChatJobStatusResponse(BaseModel):
    job_id: str
    status: str
    result: ChatResponse | None = None
    error: str | None = None


class ConversacionResumenOut(BaseModel):
    id: str
    usuario_id: int | None = None
    titulo: str
    creada_en: datetime
    actualizada_en: datetime
    total_mensajes: int = 0


class MensajeChatOut(BaseModel):
    id: int
    rol: str
    contenido: str
    archivo_almacen_url: str | None = None
    archivo_txt_url: str | None = None
    reportes_historicos: list[dict[str, str]] = Field(default_factory=list)
    creado_en: datetime


class ConversacionDetalleOut(BaseModel):
    id: str
    usuario_id: int | None = None
    titulo: str
    creada_en: datetime
    actualizada_en: datetime
    mensajes: list[MensajeChatOut] = Field(default_factory=list)
