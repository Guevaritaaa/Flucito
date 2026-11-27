"""Facturas vigentes y devoluciones del respaldo SAE, por moneda del documento."""

from collections import defaultdict
from datetime import date
from decimal import Decimal

from app.schemas.sae import CorteFacturacionSae, FacturacionMes, FacturacionMoneda, PeriodoSae, ResumenFacturacionSae
from app.services.sae.conexion import SaeNoDisponible, conectar_sae
from app.services.sae.periodos import meses_del_periodo, resolver_periodo


def consultar_facturacion(
    desde: date | None = None, hasta: date | None = None, *, moneda: str | None = None,
) -> ResumenFacturacionSae:
    with conectar_sae() as conexion:
        cursor = conexion.cursor()
        origen = cursor.execute("SELECT HUELLA, DESDE, HASTA FROM FLUCITO_SAE_CORTE_FACTURACION").fetchone()
        if origen is None or origen[1] is None or origen[2] is None:
            raise SaeNoDisponible("El respaldo carece de fechas de facturación")
        huella, primera_factura, ultima_factura = origen
        cobertura = PeriodoSae(desde=primera_factura, hasta=ultima_factura)
        periodo = resolver_periodo(desde, hasta, cobertura)

        filtro = "FECHA BETWEEN ? AND ?"
        parametros: list[date | str] = [periodo.desde, periodo.hasta]
        if moneda:
            filtro += " AND MONEDA = ?"
            parametros.append(moneda)
        cursor.execute(f"""
            SELECT EXTRACT(YEAR FROM FECHA), EXTRACT(MONTH FROM FECHA), MONEDA, TIPO,
                   SUM(DOCUMENTOS), SUM(CON_IMPORTE), SUM(IMPORTE)
            FROM FLUCITO_SAE_FACTURACION_DIA WHERE {filtro}
            GROUP BY 1, 2, 3, 4 ORDER BY 1, 2, 3, 4
        """, parametros)
        montos_mes: dict[date, dict[str, FacturacionMoneda]] = defaultdict(dict)
        montos_periodo: dict[str, FacturacionMoneda] = {}

        def acumular(totales: dict[str, FacturacionMoneda], codigo: str, tipo: str, cantidad: int, importe: Decimal) -> None:
            if codigo not in totales:
                totales[codigo] = FacturacionMoneda(moneda=codigo, facturas=0, devoluciones=0,
                                                    importe_facturado=Decimal("0.00"), importe_devoluciones=Decimal("0.00"))
            total = totales[codigo]
            if tipo == "F":
                total.facturas += cantidad
                total.importe_facturado += importe
            else:
                total.devoluciones += cantidad
                total.importe_devoluciones += importe

        for anio, mes, codigo, tipo, documentos, con_importe, importe in cursor:
            if not codigo or documentos != con_importe or importe is None:
                raise SaeNoDisponible("Hay documentos sin moneda o importe verificable en el periodo")
            acumular(montos_mes[date(anio, mes, 1)], codigo, tipo, documentos, importe)
            acumular(montos_periodo, codigo, tipo, documentos, importe)

    totales = [montos_periodo[codigo] for codigo in sorted(montos_periodo)]
    return ResumenFacturacionSae(
        corte=CorteFacturacionSae(corte_id=f"empresa02-{huella.strip()}", cobertura=cobertura),
        periodo=periodo,
        facturas=sum(total.facturas for total in totales),
        devoluciones=sum(total.devoluciones for total in totales),
        totales_por_moneda=totales,
        tendencia_mensual=[
            FacturacionMes(mes=mes, totales_por_moneda=list(montos_mes[mes].values()))
            for mes in meses_del_periodo(periodo.desde, periodo.hasta)
        ],
    )
