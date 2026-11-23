from typing import Any, Literal
from pydantic import BaseModel, Field


class RespuestaDecision(BaseModel):
    opcion: str
    recordar: bool = False
    campos: dict[str, Any] = Field(default_factory=dict)


class EnvioDecisiones(BaseModel):
    interaccion_id: str
    revision: int = Field(ge=1)
    respuestas: dict[str, RespuestaDecision] = Field(default_factory=dict)
    accion: Literal["borrador", "confirmar", "cancelar"] = "confirmar"
