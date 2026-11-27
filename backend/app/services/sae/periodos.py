"""Intervalos y cobertura para las métricas fechadas del respaldo."""

from collections.abc import Iterator
from datetime import date, timedelta

from app.schemas.sae import PeriodoSae


class PeriodoInvalido(ValueError):
    """Las fechas no forman un intervalo admitido."""


class PeriodoFueraDeCobertura(ValueError):
    def __init__(self, cobertura: PeriodoSae):
        super().__init__("El periodo solicitado queda fuera de la cobertura del respaldo.")
        self.cobertura = cobertura


def resolver_periodo(desde: date | None, hasta: date | None, cobertura: PeriodoSae) -> PeriodoSae:
    if desde is None and hasta is None:
        inicio = cobertura.hasta.replace(day=1)
        fin = inicio - timedelta(days=1)
        for _ in range(6):
            inicio = (inicio - timedelta(days=1)).replace(day=1)
        if fin < cobertura.desde:
            return cobertura
        return PeriodoSae(desde=max(inicio, cobertura.desde), hasta=fin)

    if desde is None or hasta is None or desde > hasta:
        raise PeriodoInvalido("Indica ambas fechas y coloca desde antes de o igual a hasta.")
    if desde < cobertura.desde or hasta > cobertura.hasta:
        raise PeriodoFueraDeCobertura(cobertura)
    if (hasta - desde).days >= 366:
        raise PeriodoInvalido("El periodo admite hasta 366 días, incluidas ambas fechas.")
    return PeriodoSae(desde=desde, hasta=hasta)


def meses_del_periodo(desde: date, hasta: date) -> Iterator[date]:
    mes = desde.replace(day=1)
    while mes <= hasta:
        yield mes
        mes = (mes + timedelta(days=32)).replace(day=1)
