"""Contratos del resumen de compras de Aspel SAE."""

from datetime import date
from decimal import Decimal

from pydantic import BaseModel


class PeriodoSae(BaseModel):
    desde: date
    hasta: date


class CorteComprasSae(BaseModel):
    corte_id: str
    empresa: str = "02"
    fecha_respaldo: date | None = None
    cobertura: PeriodoSae


class TotalComprasMoneda(BaseModel):
    moneda: str
    documentos: int
    importe: Decimal


class ComprasMes(BaseModel):
    mes: date
    totales_por_moneda: list[TotalComprasMoneda]


class ComprasProveedor(TotalComprasMoneda):
    clave: str | None
    nombre: str | None


class ResumenComprasSae(BaseModel):
    corte: CorteComprasSae
    periodo: PeriodoSae
    documentos: int
    totales_por_moneda: list[TotalComprasMoneda]
    tendencia_mensual: list[ComprasMes]
    principales_proveedores: list[ComprasProveedor]
