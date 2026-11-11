"""Registro central de modelos SQLAlchemy para Alembic y creación de tablas."""

from app.models.almacen import (
    ArchivoSincronizadoDrive,
    DetalleEntradaAlmacen,
    FactorLinea,
    ReporteAlmacen,
)
from app.models.catalogo_sae import (
    SaeArticulo,
    SaeClaveAlterna,
    SaeHistorialCompra,
    SaeLinea,
    SaeProveedor,
)
from app.models.conversacion import (
    ConfirmacionPendiente,
    Conversacion,
    MensajeChat,
)
from app.models.usuario import Usuario

__all__ = [
    "Usuario",
    "Conversacion",
    "MensajeChat",
    "ConfirmacionPendiente",
    "SaeLinea",
    "SaeProveedor",
    "SaeArticulo",
    "SaeClaveAlterna",
    "SaeHistorialCompra",
    "FactorLinea",
    "ReporteAlmacen",
    "DetalleEntradaAlmacen",
    "ArchivoSincronizadoDrive",
]
