"""Modelos SQLAlchemy para almacenar el Catálogo Maestro de Aspel SAE 9.0."""

from __future__ import annotations

from decimal import Decimal
from sqlalchemy import ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SaeLinea(Base):
    __tablename__ = "sae_lineas"

    clave_linea: Mapped[str] = mapped_column(String(32), primary_key=True)
    descripcion: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    estatus: Mapped[str] = mapped_column(String(8), default="A", nullable=False)


class SaeProveedor(Base):
    __tablename__ = "sae_proveedores"

    clave_proveedor: Mapped[str] = mapped_column(String(32), primary_key=True)
    nombre: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    rfc: Mapped[str] = mapped_column(String(32), index=True, default="", nullable=False)
    estatus: Mapped[str] = mapped_column(String(8), default="A", nullable=False)


class SaeArticulo(Base):
    __tablename__ = "sae_articulos"

    clave_articulo: Mapped[str] = mapped_column(String(64), primary_key=True)
    descripcion: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    clave_linea: Mapped[str | None] = mapped_column(
        String(32),
        ForeignKey("sae_lineas.clave_linea", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    unidad_entrada: Mapped[str] = mapped_column(String(32), default="PZ", nullable=False)
    cve_sat: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    cve_unidad: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    ultimo_costo: Mapped[Decimal] = mapped_column(
        Numeric(18, 6),
        default=Decimal("0.000000"),
        nullable=False,
    )
    estatus: Mapped[str] = mapped_column(String(8), default="A", nullable=False)


class SaeClaveAlterna(Base):
    __tablename__ = "sae_claves_alternas"
    __table_args__ = (
        UniqueConstraint(
            "clave_proveedor",
            "clave_alterna",
            "clave_articulo",
            name="uq_sae_claves_alternas_prov_alt_art",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    clave_alterna: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    clave_articulo: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("sae_articulos.clave_articulo", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    clave_proveedor: Mapped[str | None] = mapped_column(
        String(32),
        ForeignKey("sae_proveedores.clave_proveedor", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )


class SaeHistorialCompra(Base):
    __tablename__ = "sae_historial_compras"

    clave_proveedor: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("sae_proveedores.clave_proveedor", ondelete="CASCADE"),
        primary_key=True,
    )
    lineas_compradas_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    articulos_comprados_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
