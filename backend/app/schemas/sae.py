"""Contratos de las métricas del respaldo de Aspel SAE."""

from datetime import date
from decimal import Decimal
from typing import Literal

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


class CorteFacturacionSae(CorteComprasSae):
    """Cobertura observada en las fechas de las facturas."""


class FacturacionMoneda(BaseModel):
    moneda: str
    facturas: int
    importe_facturado: Decimal
    devoluciones: int
    importe_devoluciones: Decimal


class FacturacionMes(BaseModel):
    mes: date
    totales_por_moneda: list[FacturacionMoneda]


class ResumenFacturacionSae(BaseModel):
    corte: CorteFacturacionSae
    periodo: PeriodoSae
    facturas: int
    devoluciones: int
    totales_por_moneda: list[FacturacionMoneda]
    tendencia_mensual: list[FacturacionMes]


EstadoInventarioSae = Literal["todos", "sin_existencia", "bajo_minimo"]


class CorteInventarioSae(BaseModel):
    corte_id: str
    empresa: str = "02"
    fecha_respaldo: date | None = None
    ultimo_movimiento: date | None


class AlmacenSae(BaseModel):
    clave: int
    nombre: str


class ArticuloInventarioSae(BaseModel):
    clave: str
    nombre: str | None
    unidad: str | None
    existencia: Decimal | None
    minimo: Decimal | None


class ResumenInventarioSae(BaseModel):
    corte: CorteInventarioSae
    almacen: AlmacenSae | None
    almacenes: list[AlmacenSae]
    articulos: int
    sin_existencia: int
    bajo_minimo: int
    total_resultados: int
    pagina: int
    por_pagina: int
    existencias: list[ArticuloInventarioSae]
