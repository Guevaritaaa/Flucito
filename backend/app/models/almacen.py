"""Modelos SQLAlchemy para factores comerciales, reportes de almacén y sincronización de Drive."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class FactorLinea(Base):
    __tablename__ = "factores_linea"

    clave_linea: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("sae_lineas.clave_linea", ondelete="CASCADE"),
        primary_key=True,
    )
    nombre_factor: Mapped[str] = mapped_column(String(64), nullable=False)
    es_personalizado: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    actualizado_por_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("usuarios.id", ondelete="SET NULL"),
        nullable=True,
    )
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utc_now,
        onupdate=_utc_now,
        nullable=False,
    )


class ReporteAlmacen(Base):
    __tablename__ = "reportes_almacen"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    fecha_carpeta: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    fecha_reporte: Mapped[date | None] = mapped_column(Date, index=True, nullable=True)
    usuario_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("usuarios.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    total_articulos: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    resumen_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utc_now,
        nullable=False,
    )

    detalles: Mapped[list["DetalleEntradaAlmacen"]] = relationship(
        "DetalleEntradaAlmacen",
        back_populates="reporte",
        cascade="all, delete-orphan",
    )


class DetalleEntradaAlmacen(Base):
    __tablename__ = "detalle_entradas_almacen"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    reporte_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("reportes_almacen.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    clave_articulo: Mapped[str] = mapped_column(String(64), index=True, default="", nullable=False)
    codigo_xml_original: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    descripcion: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    linea: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    clave_proveedor: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    unidad_procesada: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    cantidad: Mapped[Decimal] = mapped_column(
        Numeric(18, 6),
        default=Decimal("0.000000"),
        nullable=False,
    )
    precio_compra: Mapped[Decimal] = mapped_column(
        Numeric(18, 6),
        default=Decimal("0.000000"),
        nullable=False,
    )
    factor_aplicado: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    precios_venta_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    origen_clave: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    origen_linea: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    origen_proveedor: Mapped[str] = mapped_column(String(64), default="", nullable=False)

    reporte: Mapped["ReporteAlmacen"] = relationship("ReporteAlmacen", back_populates="detalles")


class ArchivoSincronizadoDrive(Base):
    __tablename__ = "archivos_sincronizados_drive"

    drive_file_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    reporte_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("reportes_almacen.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    nombre: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    fecha_carpeta: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    md5_checksum: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    procesado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utc_now,
        nullable=False,
    )
