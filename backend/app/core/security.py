"""Seguridad, hashing criptográfico de contraseñas y autenticación JWT."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import secrets
from typing import Any

import jwt
from fastapi import Depends, HTTPException, Query, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.models.usuario import Usuario

try:
    import bcrypt as _bcrypt  # type: ignore[import-not-found]
except ImportError:
    _bcrypt = None

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)

_PBKDF2_ITERATIONS = 310_000


def hashear_password(password: str) -> str:
    """
    Genera un hash seguro de contraseña.
    Usa bcrypt si la extensión está disponible, o PBKDF2-HMAC-SHA256 (OpenSSL/NIST)
    cuando Control Inteligente de Aplicaciones de Windows bloquea binarios externos.
    """
    if _bcrypt is not None:
        try:
            hashed = _bcrypt.hashpw(password.encode("utf-8"), _bcrypt.gensalt())
            return hashed.decode("utf-8")
        except Exception:
            pass

    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        _PBKDF2_ITERATIONS,
    )
    return f"pbkdf2_sha256${_PBKDF2_ITERATIONS}${salt}${dk.hex()}"


def verificar_password(password_plano: str, password_hash: str) -> bool:
    """Compara una contraseña en texto plano contra su hash (bcrypt o pbkdf2_sha256)."""
    if not password_plano or not password_hash:
        return False

    if password_hash.startswith("pbkdf2_sha256$"):
        partes = password_hash.split("$")
        if len(partes) != 4:
            return False
        _, iter_str, salt, hash_hex = partes
        try:
            iteraciones = int(iter_str)
        except ValueError:
            return False
        dk = hashlib.pbkdf2_hmac(
            "sha256",
            password_plano.encode("utf-8"),
            salt.encode("utf-8"),
            iteraciones,
        )
        return hmac.compare_digest(dk.hex(), hash_hex)

    if _bcrypt is not None:
        try:
            return _bcrypt.checkpw(
                password_plano.encode("utf-8"),
                password_hash.encode("utf-8"),
            )
        except ValueError:
            return False

    return False


def crear_token_acceso(
    *,
    username: str,
    usuario_id: int,
    rol: str,
    expires_minutes: int | None = None,
) -> str:
    """Crea un token JWT firmado con HS256."""
    duracion = expires_minutes if expires_minutes is not None else settings.jwt_expire_minutes
    ahora = datetime.now(timezone.utc)
    expira = ahora + timedelta(minutes=duracion)
    payload: dict[str, Any] = {
        "sub": username,
        "uid": usuario_id,
        "rol": rol,
        "iat": int(ahora.timestamp()),
        "exp": int(expira.timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decodificar_token_acceso(token: str) -> dict[str, Any]:
    """Valida la firma y expiración del JWT y devuelve su payload."""
    try:
        return jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Tu sesión ha expirado. Inicia sesión nuevamente.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de autenticación inválido.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def obtener_usuario_opcional(
    token_header: str | None = Depends(oauth2_scheme),
    token_query: str | None = Query(default=None, alias="token"),
    db: Session = Depends(get_db),
) -> Usuario | None:
    """Devuelve el usuario autenticado si se envió un token válido, o None si no se envió."""
    token = token_header or token_query
    if not token:
        return None
    payload = decodificar_token_acceso(token)
    username = str(payload.get("sub") or "").strip()
    if not username:
        return None
    usuario = db.scalar(select(Usuario).where(Usuario.username == username))
    if usuario is None or not usuario.activo:
        return None
    return usuario


def obtener_usuario_actual(
    token_header: str | None = Depends(oauth2_scheme),
    token_query: str | None = Query(default=None, alias="token"),
    db: Session = Depends(get_db),
) -> Usuario:
    """Valida el JWT (por header Bearer o query param ?token=) y devuelve el usuario activo."""
    token = token_header or token_query
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Se requiere iniciar sesión para acceder a este recurso.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = decodificar_token_acceso(token)
    username = str(payload.get("sub") or "").strip()
    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token sin identificador de usuario.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    usuario = db.scalar(select(Usuario).where(Usuario.username == username))
    if usuario is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="El usuario asociado al token no existe.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not usuario.activo:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Esta cuenta de usuario está desactivada.",
        )
    return usuario


def requerir_admin(
    usuario_actual: Usuario = Depends(obtener_usuario_actual),
) -> Usuario:
    """Verifica que el usuario autenticado tenga rol 'admin'."""
    if usuario_actual.rol != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Se requieren permisos de administrador para realizar esta acción.",
        )
    return usuario_actual
