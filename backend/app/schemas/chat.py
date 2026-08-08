from pydantic import BaseModel


class ChatRequest(BaseModel):
    mensaje: str
    session_id: str
    cfdi_job_id: str | None = None


class ChatResponse(BaseModel):
    respuesta: str
    archivo_excel_url: str | None = None
    archivo_almacen_url: str | None = None
