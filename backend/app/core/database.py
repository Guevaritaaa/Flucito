"""Configuración de conexión a PostgreSQL con SQLAlchemy 2.0 y respaldo local automático."""

from __future__ import annotations

from collections.abc import Generator
import logging
from pathlib import Path
import socket
from urllib.parse import urlparse

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings

logger = logging.getLogger(__name__)

_RUTA_SQLITE_LOCAL = Path(__file__).resolve().parents[2] / "datos" / "flucito_local.db"


def _puerto_accesible(host: str, port: int, timeout: float = 0.6) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _normalizar_driver_postgres(url: str) -> str:
    """Usa psycopg si está disponible; si Windows Smart App Control lo bloquea, usa pg8000."""
    if not url.startswith("postgresql"):
        return url
    try:
        import psycopg  # noqa: F401

        if url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+psycopg://", 1)
        return url
    except Exception:
        if "postgresql+psycopg://" in url:
            return url.replace("postgresql+psycopg://", "postgresql+pg8000://", 1)
        if url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+pg8000://", 1)
        return url


def resolver_database_url(database_url: str | None = None) -> str:
    """
    Resuelve la URL de conexión:
    - Si apunta a PostgreSQL y el servidor está activo en el puerto indicado, usa PostgreSQL.
    - Si apunta a localhost:5432 pero el servicio local de PostgreSQL aún no está levantado,
      usa automáticamente la base SQLite local en `backend/datos/flucito_local.db` para
      permitir pruebas locales sin interrupciones.
    """
    url = (database_url or settings.database_url).strip()
    if url.startswith("sqlite"):
        return url

    parsed = urlparse(url)
    host = parsed.hostname or "localhost"
    port = parsed.port or 5432

    if host in ("localhost", "127.0.0.1") and not _puerto_accesible(host, port):
        _RUTA_SQLITE_LOCAL.parent.mkdir(parents=True, exist_ok=True)
        fallback_url = f"sqlite:///{_RUTA_SQLITE_LOCAL.as_posix()}"
        logger.warning(
            "PostgreSQL no detectado en %s:%d; usando base local SQLAlchemy en %s",
            host,
            port,
            _RUTA_SQLITE_LOCAL,
        )
        return fallback_url

    return _normalizar_driver_postgres(url)


def _crear_engine(database_url: str | None = None):
    url_efectiva = resolver_database_url(database_url)
    if url_efectiva.startswith("sqlite"):
        return create_engine(
            url_efectiva,
            connect_args={"check_same_thread": False},
        )

    return create_engine(
        url_efectiva,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
    )


engine = _crear_engine(settings.database_url)
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """Clase base para todos los modelos de SQLAlchemy."""


def get_db() -> Generator[Session, None, None]:
    """Dependencia de FastAPI que entrega una sesión de base de datos por petición."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
