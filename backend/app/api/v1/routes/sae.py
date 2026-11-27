"""Consultas autorizadas del respaldo histórico de Aspel SAE."""

from contextlib import contextmanager
from datetime import date
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from firebird.driver import DatabaseError

from app.core.security import requerir_acceso_sae
from app.schemas.sae import EstadoInventarioSae, ResumenComprasSae, ResumenFacturacionSae, ResumenInventarioSae
from app.services.sae.compras import consultar_resumen_compras
from app.services.sae.conexion import SaeNoDisponible
from app.services.sae.facturacion import consultar_facturacion
from app.services.sae.inventario import FiltroInventarioInvalido, consultar_inventario
from app.services.sae.periodos import PeriodoFueraDeCobertura, PeriodoInvalido

router = APIRouter(prefix="/sae", tags=["Aspel SAE"], dependencies=[Depends(requerir_acceso_sae)])
logger = logging.getLogger(__name__)


@contextmanager
def respuesta_sae(response: Response):
    response.headers["Cache-Control"] = "no-store"
    try:
        yield
    except PeriodoFueraDeCobertura as exc:
        raise HTTPException(status_code=422, detail={
            "codigo": "fuera_de_cobertura",
            "mensaje": str(exc),
            "cobertura": exc.cobertura.model_dump(mode="json"),
        }) from exc
    except PeriodoInvalido as exc:
        raise HTTPException(status_code=422, detail={"codigo": "periodo_invalido", "mensaje": str(exc)}) from exc
    except FiltroInventarioInvalido as exc:
        raise HTTPException(status_code=422, detail={"codigo": "filtro_invalido", "mensaje": str(exc)}) from exc
    except (SaeNoDisponible, DatabaseError) as exc:
        logger.warning("Consulta SAE indisponible (%s)", type(exc).__name__)
        raise HTTPException(status_code=503, detail={
            "codigo": "sae_no_disponible",
            "mensaje": "El respaldo de Aspel SAE no está disponible en este momento.",
        }) from exc


@router.get("/resumen", response_model=ResumenComprasSae)
def resumen_sae(response: Response, desde: date | None = None, hasta: date | None = None) -> ResumenComprasSae:
    with respuesta_sae(response):
        return consultar_resumen_compras(desde, hasta)


@router.get("/facturacion", response_model=ResumenFacturacionSae)
def facturacion_sae(response: Response, desde: date | None = None, hasta: date | None = None) -> ResumenFacturacionSae:
    with respuesta_sae(response):
        return consultar_facturacion(desde, hasta)


@router.get("/inventario", response_model=ResumenInventarioSae)
def inventario_sae(
    response: Response,
    almacen: Annotated[int | None, Query(ge=1)] = None,
    articulo: Annotated[str | None, Query(max_length=100)] = None,
    estado: EstadoInventarioSae = "todos",
    pagina: Annotated[int, Query(ge=1)] = 1,
    por_pagina: Annotated[int, Query(ge=1, le=50)] = 20,
) -> ResumenInventarioSae:
    with respuesta_sae(response):
        return consultar_inventario(almacen=almacen, articulo=articulo, estado=estado, pagina=pagina, por_pagina=por_pagina)
