"""Modelos para guardar conversaciones, mensajes del chat y confirmaciones pendientes por usuario."""

from __future__ import annotations

from datetime import datetime, timezone
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Conversacion(Base):
    __tablename__ = "conversaciones"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    usuario_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("usuarios.id", ondelete="CASCADE"),
        index=True,
        nullable=True,
    )
    titulo: Mapped[str] = mapped_column(String(255), default="Nueva conversación", nullable=False)
    creada_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utc_now,
        nullable=False,
    )
    actualizada_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utc_now,
        onupdate=_utc_now,
        nullable=False,
    )

    mensajes: Mapped[list["MensajeChat"]] = relationship(
        "MensajeChat",
        back_populates="conversacion",
        cascade="all, delete-orphan",
        order_by="MensajeChat.id.asc()",
    )


class MensajeChat(Base):
    __tablename__ = "mensajes_chat"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversacion_id: Mapped[str] = mapped_column(
        String(128),
        ForeignKey("conversaciones.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    rol: Mapped[str] = mapped_column(String(32), nullable=False)
    contenido: Mapped[str] = mapped_column(Text, nullable=False)
    metadatos_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utc_now,
        nullable=False,
    )

    conversacion: Mapped["Conversacion"] = relationship("Conversacion", back_populates="mensajes")


class ConfirmacionPendiente(Base):
    __tablename__ = "confirmaciones_pendientes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversacion_id: Mapped[str] = mapped_column(
        String(128),
        unique=True,
        index=True,
        nullable=False,
    )
    usuario_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("usuarios.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    datos_json: Mapped[str] = mapped_column(Text, nullable=False)
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utc_now,
        onupdate=_utc_now,
        nullable=False,
    )
