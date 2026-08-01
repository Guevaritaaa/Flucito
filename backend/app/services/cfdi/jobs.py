"""Almacen temporal de archivos CFDI cargados para el asistente."""

from __future__ import annotations

import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4


@dataclass
class CFDIJob:
    directorio: Path
    rutas_xml: list[Path]
    ruta_salida: Path
    creado_en: float


CFDI_JOBS: dict[str, CFDIJob] = {}
JOB_TTL_SECONDS = 30 * 60


def crear_job(directorio: Path, rutas_xml: list[Path]) -> str:
    """Registra archivos ya guardados y devuelve identificador opaco."""
    limpiar_jobs_expirados()
    job_id = uuid4().hex
    CFDI_JOBS[job_id] = CFDIJob(
        directorio=directorio,
        rutas_xml=rutas_xml,
        ruta_salida=directorio / "reporte_cfdi.xlsx",
        creado_en=time.monotonic(),
    )
    return job_id


def obtener_job(job_id: str) -> CFDIJob | None:
    limpiar_jobs_expirados()
    return CFDI_JOBS.get(job_id)


def limpiar_jobs_expirados() -> None:
    """Elimina jobs sin actividad después del TTL configurado."""
    ahora = time.monotonic()
    expirados = [
        job_id
        for job_id, job in CFDI_JOBS.items()
        if ahora - job.creado_en >= JOB_TTL_SECONDS
    ]
    for job_id in expirados:
        eliminar_job(job_id)


def eliminar_job(job_id: str) -> None:
    """Elimina registro y archivos temporales del job."""
    job = CFDI_JOBS.pop(job_id, None)
    if job is not None:
        shutil.rmtree(job.directorio, ignore_errors=True)
