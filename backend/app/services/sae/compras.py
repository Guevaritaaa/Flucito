"""Métricas de compras por fecha del documento, en su moneda original."""

from collections import defaultdict
from datetime import date
from typing import Literal

from app.schemas.sae import (
    ComprasMes,
    ComprasProveedor,
    CorteComprasSae,
    PeriodoSae,
    ResumenComprasSae,
    TotalComprasMoneda,
)
from app.services.sae.conexion import SaeNoDisponible, conectar_sae
from app.services.sae.periodos import meses_del_periodo, resolver_periodo


def consultar_resumen_compras(
    desde: date | None = None,
    hasta: date | None = None,
    *,
    moneda: str | None = None,
    proveedor: str | None = None,
    orden_proveedores: Literal["documentos", "importe"] = "importe",
) -> ResumenComprasSae:
    with conectar_sae() as conexion:
        cursor = conexion.cursor()
        origen = cursor.execute("SELECT HUELLA, DESDE, HASTA FROM FLUCITO_SAE_CORTE_COMPRAS").fetchone()
        if origen is None or origen[1] is None or origen[2] is None:
            raise SaeNoDisponible("El respaldo carece de fechas de compras")

        huella, primera_compra, ultima_compra = origen
        cobertura = PeriodoSae(desde=primera_compra, hasta=ultima_compra)
        periodo = resolver_periodo(desde, hasta, cobertura)
        fechas = (periodo.desde, periodo.hasta)
        condiciones = ["FECHA BETWEEN ? AND ?"]
        parametros = list(fechas)
        if moneda:
            condiciones.append("MONEDA = ?")
            parametros.append(moneda)
        if proveedor:
            condiciones.append("(PROVEEDOR_CLAVE = CAST(? AS VARCHAR(100)) OR PROVEEDOR_NOMBRE CONTAINING CAST(? AS VARCHAR(100)))")
            parametros.extend((proveedor, proveedor))
        filtro = " AND ".join(condiciones)

        totales = []
        orden_ranking = "SUM(DOCUMENTOS)" if orden_proveedores == "documentos" else "SUM(IMPORTE)"
        cursor.execute(f"""
            SELECT MONEDA, SUM(DOCUMENTOS), SUM(CON_IMPORTE), SUM(IMPORTE)
            FROM FLUCITO_SAE_COMPRAS_DIA WHERE {filtro}
            GROUP BY MONEDA ORDER BY MONEDA
        """, parametros)
        for codigo, documentos, con_importe, importe in cursor:
            if not codigo or con_importe != documentos or importe is None:
                raise SaeNoDisponible("Hay compras sin moneda o importe verificable en el periodo")
            totales.append(TotalComprasMoneda(moneda=codigo, documentos=documentos, importe=importe))

        meses: dict[date, list[TotalComprasMoneda]] = defaultdict(list)
        cursor.execute(f"""
            SELECT EXTRACT(YEAR FROM FECHA), EXTRACT(MONTH FROM FECHA), MONEDA,
                   SUM(DOCUMENTOS), SUM(IMPORTE)
            FROM FLUCITO_SAE_COMPRAS_DIA WHERE {filtro}
            GROUP BY 1, 2, 3 ORDER BY 1, 2, 3
        """, parametros)
        for anio, mes, moneda, documentos, importe in cursor:
            meses[date(anio, mes, 1)].append(
                TotalComprasMoneda(moneda=moneda, documentos=documentos, importe=importe)
            )

        cursor.execute(f"""
            SELECT MONEDA, PROVEEDOR_CLAVE, PROVEEDOR_NOMBRE, DOCUMENTOS, IMPORTE
            FROM (
                SELECT MONEDA, PROVEEDOR_CLAVE, PROVEEDOR_NOMBRE,
                       SUM(DOCUMENTOS) AS DOCUMENTOS, SUM(IMPORTE) AS IMPORTE,
                       ROW_NUMBER() OVER (
                           PARTITION BY MONEDA ORDER BY {orden_ranking} DESC, PROVEEDOR_CLAVE
                       ) AS POSICION
                FROM FLUCITO_SAE_COMPRAS_DIA WHERE {filtro}
                GROUP BY MONEDA, PROVEEDOR_CLAVE, PROVEEDOR_NOMBRE
            ) RANKING
            WHERE POSICION <= 5 ORDER BY MONEDA, POSICION
        """, parametros)
        proveedores = [
            ComprasProveedor(moneda=moneda, clave=clave, nombre=nombre, documentos=documentos, importe=importe)
            for moneda, clave, nombre, documentos, importe in cursor
        ]

    return ResumenComprasSae(
        corte=CorteComprasSae(corte_id=f"empresa02-{huella.strip()}", cobertura=cobertura),
        periodo=periodo,
        documentos=sum(total.documentos for total in totales),
        totales_por_moneda=totales,
        tendencia_mensual=[ComprasMes(mes=mes, totales_por_moneda=meses[mes]) for mes in meses_del_periodo(*fechas)],
        principales_proveedores=proveedores,
    )
