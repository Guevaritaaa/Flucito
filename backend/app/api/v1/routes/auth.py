"""Rutas de autenticación JWT (/login, /me) y gestión de cuentas de usuario (/usuarios)."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import (
    crear_token_acceso,
    hashear_password,
    obtener_usuario_actual,
    requerir_admin,
    verificar_password,
)
from app.models.usuario import Usuario
from app.schemas.auth import (
    TokenResponse,
    UsuarioCreateRequest,
    UsuarioOut,
    UsuarioUpdateRequest,
)

router = APIRouter(prefix="/auth", tags=["Autenticación y Usuarios"])


async def _extraer_credenciales(request: Request) -> tuple[str, str]:
    """Soporta tanto JSON (`application/json`) como formulario OAuth2 (`x-www-form-urlencoded`)."""
    content_type = (request.headers.get("content-type") or "").lower()
    if "application/json" in content_type:
        try:
            body = await request.json()
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Formato JSON inválido en inicio de sesión.",
            ) from exc
        if not isinstance(body, dict):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Se esperaba un objeto JSON con username y password.",
            )
        username = str(body.get("username") or "").strip().lower()
        password = str(body.get("password") or "")
        return username, password

    form = await request.form()
    username = str(form.get("username") or "").strip().lower()
    password = str(form.get("password") or "")
    return username, password


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Inicia sesión con usuario y contraseña y devuelve un token JWT",
    openapi_extra={
        "requestBody": {
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "required": ["username", "password"],
                        "properties": {
                            "username": {"type": "string", "example": "robert"},
                            "password": {"type": "string", "example": "Interflu2026!"},
                        },
                    }
                },
                "application/x-www-form-urlencoded": {
                    "schema": {
                        "type": "object",
                        "required": ["username", "password"],
                        "properties": {
                            "username": {"type": "string"},
                            "password": {"type": "string"},
                        },
                    }
                },
            }
        }
    },
)
async def iniciar_sesion(
    request: Request,
    db: Session = Depends(get_db),
) -> TokenResponse:
    """Autentica al usuario y entrega el token JWT junto con su perfil."""
    username, password = await _extraer_credenciales(request)
    if not username or not password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Debes ingresar usuario y contraseña.",
        )

    usuario = db.scalar(select(Usuario).where(Usuario.username == username))
    if usuario is None or not verificar_password(password, usuario.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario o contraseña incorrectos.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not usuario.activo:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tu cuenta de usuario está desactivada. Contacta al administrador.",
        )

    usuario.ultimo_login = datetime.now(timezone.utc)
    db.commit()
    db.refresh(usuario)

    token = crear_token_acceso(
        username=usuario.username,
        usuario_id=usuario.id,
        rol=usuario.rol,
    )
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        usuario=UsuarioOut.model_validate(usuario),
    )


@router.get(
    "/me",
    response_model=UsuarioOut,
    summary="Obtiene la información del usuario autenticado actualmente",
)
def obtener_perfil_actual(
    usuario_actual: Usuario = Depends(obtener_usuario_actual),
) -> UsuarioOut:
    """Devuelve los datos del usuario dueño del token JWT actual."""
    return UsuarioOut.model_validate(usuario_actual)


@router.get(
    "/usuarios",
    response_model=list[UsuarioOut],
    summary="Lista todos los usuarios registrados (solo administradores)",
)
def listar_usuarios(
    _: Usuario = Depends(requerir_admin),
    db: Session = Depends(get_db),
) -> list[UsuarioOut]:
    """Devuelve la lista de usuarios ordenada por ID."""
    usuarios = db.scalars(select(Usuario).order_by(Usuario.id.asc())).all()
    return [UsuarioOut.model_validate(u) for u in usuarios]


@router.post(
    "/usuarios",
    response_model=UsuarioOut,
    status_code=status.HTTP_201_CREATED,
    summary="Crea una nueva cuenta de usuario (solo administradores)",
)
def crear_usuario(
    payload: UsuarioCreateRequest,
    _: Usuario = Depends(requerir_admin),
    db: Session = Depends(get_db),
) -> UsuarioOut:
    """Registra un nuevo usuario ('admin' u 'operador')."""
    username_limpio = payload.username.strip().lower()
    existente = db.scalar(select(Usuario).where(Usuario.username == username_limpio))
    if existente is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Ya existe un usuario con el nombre '{username_limpio}'.",
        )

    nuevo = Usuario(
        username=username_limpio,
        nombre_completo=payload.nombre_completo.strip(),
        password_hash=hashear_password(payload.password),
        rol=payload.rol,
        activo=True,
    )
    db.add(nuevo)
    db.commit()
    db.refresh(nuevo)
    return UsuarioOut.model_validate(nuevo)


@router.patch(
    "/usuarios/{usuario_id}",
    response_model=UsuarioOut,
    summary="Actualiza datos, rol o estado activo de un usuario (solo administradores)",
)
def actualizar_usuario(
    usuario_id: int,
    payload: UsuarioUpdateRequest,
    admin_actual: Usuario = Depends(requerir_admin),
    db: Session = Depends(get_db),
) -> UsuarioOut:
    """Permite cambiar contraseña, rol o desactivar/activar a un usuario."""
    usuario = db.scalar(select(Usuario).where(Usuario.id == usuario_id))
    if usuario is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado.",
        )

    if payload.activo is False and usuario.id == admin_actual.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No puedes desactivar tu propia cuenta de administrador.",
        )

    if payload.nombre_completo is not None:
        usuario.nombre_completo = payload.nombre_completo.strip()
    if payload.password is not None:
        usuario.password_hash = hashear_password(payload.password)
    if payload.rol is not None:
        usuario.rol = payload.rol
    if payload.activo is not None:
        usuario.activo = payload.activo

    db.commit()
    db.refresh(usuario)
    return UsuarioOut.model_validate(usuario)
