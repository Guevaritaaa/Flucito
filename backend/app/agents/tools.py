"""Tools disponibles para agente Flucito."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from langchain_core.tools import tool

from app.core.config import settings
from app.services.almacen.excel import (
    CARPETA_DATOS,
    NOMBRE_ARCHIVO_RESUMEN,
    procesar_carpeta,
)
from app.services.almacen.fuentes.sincronizador import sincronizar_drive

logger = logging.getLogger(__name__)


@tool
def generar_entradas_almacen() -> str:
    """Genera Excel acumulativo y resumen JSON desde local o Google Drive."""
    usar_drive = bool(
        settings.google_drive_folder_id
        and (
            settings.google_oauth_client_json
            or settings.google_oauth_client_file
            or settings.google_service_account_json
            or settings.google_service_account_file
        )
    )
    logger.info("Tool 'generar_entradas_almacen' invocada. Modo Google Drive: %s", usar_drive)

    if usar_drive:
        try:
            sincronizacion = sincronizar_drive()
        except (OSError, RuntimeError, ValueError) as error:
            logger.exception("Error durante sincronización con Drive: %s", error)
            return json.dumps(
                {"ok": False, "error": str(error)},
                ensure_ascii=False,
            )
        if sincronizacion["carpetas"] == 0:
            logger.warning("Drive: No se encontraron subcarpetas con documentos.")
            return json.dumps(
                {"ok": False, "error": "No hay subcarpetas con documentos en Google Drive"},
                ensure_ascii=False,
            )
        if sincronizacion.get("carpetas_nuevas", 0) == 0:
            logger.info("Drive: Sin documentos nuevos. Verificando si existe base previa...")
            ruta_resumen = Path(CARPETA_DATOS) / NOMBRE_ARCHIVO_RESUMEN
            ruta_base = Path(CARPETA_DATOS) / "BASE_ENTRADAS_ALMACEN.xlsx"
            if ruta_base.is_file() and ruta_resumen.is_file():
                try:
                    resumen = json.loads(ruta_resumen.read_text(encoding="utf-8"))
                    resumen["origen"] = "google_drive"
                    resumen["documentos_nuevos"] = 0
                    return json.dumps(
                        {
                            "ok": True,
                            "reporte_generado": True,
                            "documentos_nuevos": 0,
                            "mensaje": "No hay documentos nuevos en Google Drive. La base acumulada ya está al día.",
                            "resumen": resumen,
                        },
                        ensure_ascii=False,
                    )
                except (OSError, ValueError):
                    pass

            logger.info("Drive: No hay documentos nuevos ni base previa generada.")
            return json.dumps(
                {
                    "ok": True,
                    "reporte_generado": False,
                    "documentos_nuevos": 0,
                    "mensaje": "No hay documentos nuevos en Google Drive",
                },
                ensure_ascii=False,
            )

    else:
        sincronizacion = {"origen": "local"}
    carpeta = Path(CARPETA_DATOS)
    if not usar_drive and not carpeta.is_dir():
        logger.warning("Carpeta local de almacén no encontrada: %s", carpeta)
        return json.dumps(
            {"ok": False, "error": "Carpeta de almacén no encontrada"},
            ensure_ascii=False,
        )

    if not usar_drive and not list(carpeta.glob("*.xml")):
        logger.warning("No hay archivos XML en la carpeta local: %s", carpeta)
        return json.dumps(
            {"ok": False, "error": "No hay XML en la carpeta de almacén"},
            ensure_ascii=False,
        )

    try:
        if not usar_drive:
            logger.info("Procesando carpeta local: %s", carpeta)
            procesar_carpeta(carpeta)
        ruta_resumen = carpeta / NOMBRE_ARCHIVO_RESUMEN
        if not ruta_resumen.is_file():
            logger.error("No se encontró el archivo de resumen esperado en %s", ruta_resumen)
            return json.dumps(
                {"ok": False, "error": "No se pudo generar el resumen de almacén"},
                ensure_ascii=False,
            )
        resumen = json.loads(ruta_resumen.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        logger.exception("Error al leer resumen o procesar almacén: %s", error)
        return json.dumps(
            {"ok": False, "error": str(error)},
            ensure_ascii=False,
        )

    if usar_drive:
        resumen["origen"] = "google_drive"
        resumen["documentos_nuevos"] = sincronizacion["archivos"]
        resumen["carpetas_drive"] = sincronizacion["carpetas"]
        resumen["archivos_drive"] = sincronizacion["archivos"]

    logger.info("Tool 'generar_entradas_almacen' completada exitosamente.")
    return json.dumps(
        {
            "ok": True,
            "reporte_generado": True,
            "resumen": resumen,
        },
        ensure_ascii=False,
    )
