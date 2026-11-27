"""Métricas de compras por fecha del documento, en su moneda original."""

from collections import defaultdict
from collections.abc import Iterator
from datetime import date, timedelta

from app.schemas.sae import (
    ComprasMes,
    ComprasProveedor,
    CorteComprasSae,
    PeriodoSae,
    ResumenComprasSae,
    TotalComprasMoneda,
)
from app.services.sae.conexion import SaeNoDisponible, conectar_sae


class PeriodoComprasInvalido(ValueError):
    """Las fechas no forman un intervalo admitido."""


class PeriodoFueraDeCobertura(ValueError):
    def __init__(self, cobertura: PeriodoSae):
        super().__init__("El periodo solicitado queda fuera de la cobertura del respaldo de compras.")
        self.cobertura = cobertura


def _periodo_compras(desde: date | None, hasta: date | None, cobertura: PeriodoSae) -> PeriodoSae:
    if desde is None and hasta is None:
        # Los seis meses completos previos al mes de la última compra registrada.
        inicio = cobertura.hasta.replace(day=1)
        fin = inicio - timedelta(days=1)
        for _ in range(6):
            inicio = (inicio - timedelta(days=1)).replace(day=1)
        if fin < cobertura.desde:
            return cobertura
        return PeriodoSae(desde=max(inicio, cobertura.desde), hasta=fin)

    if desde is None or hasta is None or desde > hasta:
        raise PeriodoComprasInvalido("Indica ambas fechas y coloca desde antes de o igual a hasta.")
    if desde < cobertura.desde or hasta > cobertura.hasta:
        raise PeriodoFueraDeCobertura(cobertura)
    if (hasta - desde).days >= 366:
        raise PeriodoComprasInvalido("El periodo admite hasta 366 días, incluidas ambas fechas.")
    return PeriodoSae(desde=desde, hasta=hasta)


def _meses(desde: date, hasta: date) -> Iterator[date]:
    mes = desde.replace(day=1)
    while mes <= hasta:
        yield mes
        mes = (mes + timedelta(days=32)).replace(day=1)


def consultar_resumen_compras(desde: date | None = None, hasta: date | None = None) -> ResumenComprasSae:
    with conectar_sae() as conexion:
        cursor = conexion.cursor()
        origen = cursor.execute("SELECT HUELLA, DESDE, HASTA FROM FLUCITO_SAE_CORTE_COMPRAS").fetchone()
        if origen is None or origen[1] is None or origen[2] is None:
            raise SaeNoDisponible("El respaldo carece de fechas de compras")

        huella, primera_compra, ultima_compra = origen
        cobertura = PeriodoSae(desde=primera_compra, hasta=ultima_compra)
        periodo = _periodo_compras(desde, hasta, cobertura)
        fechas = (periodo.desde, periodo.hasta)

        totales = []
        cursor.execute("""
            SELECT MONEDA, SUM(DOCUMENTOS), SUM(CON_IMPORTE), SUM(IMPORTE)
            FROM FLUCITO_SAE_COMPRAS_DIA WHERE FECHA BETWEEN ? AND ?
            GROUP BY MONEDA ORDER BY MONEDA
        """, fechas)
        for moneda, documentos, con_importe, importe in cursor:
            if not moneda or con_importe != documentos or importe is None:
                raise SaeNoDisponible("Hay compras sin moneda o importe verificable en el periodo")
            totales.append(TotalComprasMoneda(moneda=moneda, documentos=documentos, importe=importe))

        meses: dict[date, list[TotalComprasMoneda]] = defaultdict(list)
        cursor.execute("""
            SELECT EXTRACT(YEAR FROM FECHA), EXTRACT(MONTH FROM FECHA), MONEDA,
                   SUM(DOCUMENTOS), SUM(IMPORTE)
            FROM FLUCITO_SAE_COMPRAS_DIA WHERE FECHA BETWEEN ? AND ?
            GROUP BY 1, 2, 3 ORDER BY 1, 2, 3
        """, fechas)
        for anio, mes, moneda, documentos, importe in cursor:
            meses[date(anio, mes, 1)].append(
                TotalComprasMoneda(moneda=moneda, documentos=documentos, importe=importe)
            )

        cursor.execute("""
            SELECT MONEDA, PROVEEDOR_CLAVE, PROVEEDOR_NOMBRE, DOCUMENTOS, IMPORTE
            FROM (
                SELECT MONEDA, PROVEEDOR_CLAVE, PROVEEDOR_NOMBRE,
                       SUM(DOCUMENTOS) AS DOCUMENTOS, SUM(IMPORTE) AS IMPORTE,
                       ROW_NUMBER() OVER (
                           PARTITION BY MONEDA ORDER BY SUM(IMPORTE) DESC, PROVEEDOR_CLAVE
                       ) AS POSICION
                FROM FLUCITO_SAE_COMPRAS_DIA WHERE FECHA BETWEEN ? AND ?
                GROUP BY MONEDA, PROVEEDOR_CLAVE, PROVEEDOR_NOMBRE
            ) RANKING
            WHERE POSICION <= 5 ORDER BY MONEDA, POSICION
        """, fechas)
        proveedores = [
            ComprasProveedor(moneda=moneda, clave=clave, nombre=nombre, documentos=documentos, importe=importe)
            for moneda, clave, nombre, documentos, importe in cursor
        ]

    return ResumenComprasSae(
        corte=CorteComprasSae(corte_id=f"empresa02-{huella.strip()}", cobertura=cobertura),
        periodo=periodo,
        documentos=sum(total.documentos for total in totales),
        totales_por_moneda=totales,
        tendencia_mensual=[ComprasMes(mes=mes, totales_por_moneda=meses[mes]) for mes in _meses(*fechas)],
        principales_proveedores=proveedores,
    )
