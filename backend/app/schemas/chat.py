from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    mensaje: str
    session_id: str


class ChatResponse(BaseModel):
    respuesta: str
    archivo_almacen_url: str | None = None
    archivo_txt_url: str | None = None
    reportes_historicos: list[dict[str, str]] = Field(default_factory=list)
