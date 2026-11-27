"""Consultas autorizadas del respaldo histórico de Aspel SAE."""

from datetime import date
import logging

from fastapi import APIRouter, Depends, HTTPException, Response
from firebird.driver import DatabaseError

from app.core.security import requerir_acceso_sae
from app.schemas.sae import ResumenComprasSae
from app.services.sae.compras import PeriodoComprasInvalido, PeriodoFueraDeCobertura, consultar_resumen_compras
from app.services.sae.conexion import SaeNoDisponible

router = APIRouter(prefix="/sae", tags=["Aspel SAE"], dependencies=[Depends(requerir_acceso_sae)])
logger = logging.getLogger(__name__)


@router.get("/resumen", response_model=ResumenComprasSae)
def resumen_sae(response: Response, desde: date | None = None, hasta: date | None = None) -> ResumenComprasSae:
    try:
        resumen = consultar_resumen_compras(desde, hasta)
    except PeriodoFueraDeCobertura as exc:
        raise HTTPException(status_code=422, detail={
            "codigo": "fuera_de_cobertura",
            "mensaje": str(exc),
            "cobertura": exc.cobertura.model_dump(mode="json"),
        }) from exc
    except PeriodoComprasInvalido as exc:
        raise HTTPException(status_code=422, detail={"codigo": "periodo_invalido", "mensaje": str(exc)}) from exc
    except (SaeNoDisponible, DatabaseError) as exc:
        logger.warning("Resumen de compras SAE indisponible (%s)", type(exc).__name__)
        raise HTTPException(status_code=503, detail={
            "codigo": "sae_no_disponible",
            "mensaje": "El respaldo de Aspel SAE no está disponible en este momento.",
        }) from exc

    response.headers["Cache-Control"] = "no-store"
    return resumen
