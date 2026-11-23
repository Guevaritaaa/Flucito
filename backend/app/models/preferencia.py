"""Preferencias personales; no alteran los factores compartidos de SAE."""
from sqlalchemy import ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class PreferenciaDecision(Base):
    __tablename__ = "preferencias_decision"
    __table_args__ = (UniqueConstraint("usuario_id", "clave"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id", ondelete="CASCADE"), index=True)
    clave: Mapped[str] = mapped_column(String(128))
    respuesta_json: Mapped[str] = mapped_column(Text)
