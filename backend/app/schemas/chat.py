from datetime import datetime
from pydantic import BaseModel, Field
from app.schemas.decisiones import EnvioDecisiones


class ChatRequest(BaseModel):
    mensaje: str
    session_id: str
    decisiones: EnvioDecisiones | None = None


class ActividadChat(BaseModel):
    texto: str
    estado: str
    id: str | None = None
    tipo: str | None = None
    funcion: str | None = None
    resumen: str | None = None
    resumen_idioma: str | None = None


class ChatResponse(BaseModel):
    respuesta: str
    avisos: list[dict[str, str]] = Field(default_factory=list)
    interaccion: dict | None = None
    revision_reporte: dict | None = None
    archivo_almacen_url: str | None = None
    archivo_txt_url: str | None = None
    reportes_historicos: list[dict[str, str]] = Field(default_factory=list)
    actividades: list[ActividadChat] = Field(default_factory=list)


class ChatJobCreateResponse(BaseModel):
    job_id: str
    status: str


class ChatJobStatusResponse(BaseModel):
    job_id: str
    status: str
    result: ChatResponse | None = None
    error: str | None = None
    etapa: str = "pensando"
    actividades: list[ActividadChat] = Field(default_factory=list)
    texto_provisional: str = ""


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
    avisos: list[dict[str, str]] = Field(default_factory=list)
    interaccion: dict | None = None
    revision_reporte: dict | None = None
    archivo_almacen_url: str | None = None
    archivo_txt_url: str | None = None
    reportes_historicos: list[dict[str, str]] = Field(default_factory=list)
    creado_en: datetime
    actividades: list[ActividadChat] = Field(default_factory=list)


class ConversacionDetalleOut(BaseModel):
    id: str
    usuario_id: int | None = None
    titulo: str
    creada_en: datetime
    actualizada_en: datetime
    mensajes: list[MensajeChatOut] = Field(default_factory=list)
