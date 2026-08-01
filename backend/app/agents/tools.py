"""Tools disponibles para agente Flucito."""

from __future__ import annotations

import json
from pathlib import Path

from langchain_core.tools import tool

from app.services.cfdi.extractor import generar_excel_desde_xmls
from app.services.cfdi.jobs import obtener_job


@tool
def generar_reporte_cfdi(rutas_xml: list[str], ruta_salida: str) -> str:
    """Procesa XML CFDI 4.0 y genera reporte Excel."""
    if not rutas_xml:
        return json.dumps(
            {"ok": False, "error": "No se recibieron XMLs"},
            ensure_ascii=False,
        )

    archivos = [Path(ruta) for ruta in rutas_xml]
    faltantes = [str(ruta) for ruta in archivos if not ruta.is_file()]

    if faltantes:
        return json.dumps(
            {
                "ok": False,
                "error": "Archivos no encontrados",
                "archivos": faltantes,
            },
            ensure_ascii=False,
        )

    try:
        resultado = generar_excel_desde_xmls(
            archivos,
            Path(ruta_salida),
        )
    except (OSError, ValueError) as error:
        return json.dumps(
            {"ok": False, "error": str(error)},
            ensure_ascii=False,
        )

    return json.dumps(
        {
            "ok": True,
            "archivo_excel": str(resultado.archivo_excel),
            "comprobantes": resultado.comprobantes,
            "conceptos": resultado.conceptos,
            "impuestos": resultado.impuestos,
            "errores": resultado.errores,
        },
        ensure_ascii=False,
    )


@tool
def generar_reporte_cfdi_job(job_id: str) -> str:
    """Genera reporte Excel usando XML previamente cargados en un job CFDI."""
    job = obtener_job(job_id)
    if job is None:
        return json.dumps(
            {"ok": False, "error": "Job CFDI no encontrado"},
            ensure_ascii=False,
        )

    resultado = generar_reporte_cfdi.invoke(
        {
            "rutas_xml": [str(ruta) for ruta in job.rutas_xml],
            "ruta_salida": str(job.ruta_salida),
        }
    )
    datos = json.loads(resultado)
    if datos.get("ok"):
        datos = {
            "ok": True,
            "reporte_generado": True,
            "job_id": job_id,
            "comprobantes": datos.get("comprobantes", 0),
            "conceptos": datos.get("conceptos", 0),
            "impuestos": datos.get("impuestos", 0),
            "errores": datos.get("errores", 0),
        }
    return json.dumps(datos, ensure_ascii=False)
