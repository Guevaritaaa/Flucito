"""Esquemas Pydantic para autenticación JWT y administración de usuarios."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

RolUsuario = Literal["admin", "operador"]


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1, max_length=128)


class UsuarioOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    nombre_completo: str
    rol: str
    activo: bool
    creado_en: datetime
    ultimo_login: datetime | None = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    usuario: UsuarioOut


class UsuarioCreateRequest(BaseModel):
    username: str = Field(..., min_length=2, max_length=64)
    nombre_completo: str = Field(..., min_length=2, max_length=150)
    password: str = Field(..., min_length=6, max_length=128)
    rol: RolUsuario = "operador"


class UsuarioUpdateRequest(BaseModel):
    nombre_completo: str | None = Field(default=None, min_length=2, max_length=150)
    password: str | None = Field(default=None, min_length=6, max_length=128)
    rol: RolUsuario | None = None
    activo: bool | None = None
