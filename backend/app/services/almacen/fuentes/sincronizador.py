"""Sincroniza subcarpetas Drive con el pipeline local de almacén."""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Any

import pandas as pd

from app.services.almacen.excel import (
    CARPETA_DATOS,
    NOMBRE_ARCHIVO_BASE,
    guardar_en_base_acumulada,
    procesar_xml,
)
from app.services.almacen.fuentes.google_drive_client import (
    crear_cliente_drive,
    descargar_archivo,
    listar_carpetas_factura,
)
from app.services.almacen.fuentes.estado_drive import (
    NOMBRE_ESTADO,
    cargar_estado,
    carpetas_con_novedades,
    guardar_estado,
    marcar_procesadas,
)

logger = logging.getLogger(__name__)


def sincronizar_drive(cliente: Any | None = None, forzar: bool = False) -> dict:
    """Descarga carpetas Drive temporalmente y actualiza base acumulada local."""
    logger.info("Iniciando sincronización con Google Drive...")
    cliente = cliente or crear_cliente_drive()
    carpetas = listar_carpetas_factura(cliente)
    if not carpetas:
        logger.info("Drive: 0 carpetas encontradas en la carpeta raíz.")
        return {"carpetas": 0, "archivos": 0, "productos": 0}

    logger.info("Drive: %d carpeta(s) encontrada(s) en total.", len(carpetas))

    ruta_estado = Path(CARPETA_DATOS) / NOMBRE_ESTADO
    ruta_excel = Path(CARPETA_DATOS) / NOMBRE_ARCHIVO_BASE

    if forzar or not ruta_excel.is_file():
        if not ruta_excel.is_file():
            logger.info("No existe %s. Auto-recuperación: forzando lectura completa de Drive.", NOMBRE_ARCHIVO_BASE)
        else:
            logger.info("Sincronización forzada solicitada. Limpiando estado previo.")
        estado = {"archivos": {}}
    else:
        estado = cargar_estado(ruta_estado)

    carpetas_nuevas = carpetas_con_novedades(carpetas, estado)
    if not carpetas_nuevas:
        logger.info("Drive: Todas las carpetas están al día. 0 carpetas con novedades.")
        return {
            "carpetas": len(carpetas),
            "carpetas_nuevas": 0,
            "archivos": 0,
            "productos": 0,
        }

    logger.info("Drive: %d carpeta(s) con archivos nuevos o modificados.", len(carpetas_nuevas))

    dataframes: list[pd.DataFrame] = []
    archivos_descargados = 0
    with tempfile.TemporaryDirectory(prefix="flucito_drive_almacen_") as temporal:
        raiz = Path(temporal)
        for carpeta in carpetas_nuevas:
            logger.info("Procesando carpeta Drive: %s (id: %s)", carpeta.nombre, carpeta.id)
            destino = raiz / carpeta.id
            destino.mkdir(parents=True, exist_ok=True)
            rutas_xml: list[Path] = []
            for archivo in carpeta.archivos:
                ruta = destino / Path(archivo.nombre).name
                logger.info("  Descargando archivo: %s", archivo.nombre)
                descargar_archivo(cliente, archivo, ruta)
                archivos_descargados += 1
                if archivo.extension == ".xml":
                    rutas_xml.append(ruta)

            for ruta_xml in rutas_xml:
                logger.info("  Extrayendo datos de XML: %s", ruta_xml.name)
                dataframes.append(procesar_xml(str(ruta_xml), str(destino)))

    if not dataframes:
        logger.warning("No se obtuvieron productos de las carpetas nuevas.")
        return {
            "carpetas": len(carpetas_nuevas),
            "carpetas_nuevas": len(carpetas_nuevas),
            "archivos": archivos_descargados,
            "productos": 0,
        }

    df_nuevo = pd.concat(dataframes, ignore_index=True)
    guardar_en_base_acumulada(df_nuevo, CARPETA_DATOS)
    marcar_procesadas(carpetas_nuevas, estado)
    guardar_estado(ruta_estado, estado)
    logger.info(
        "Sincronización finalizada con éxito: %d carpetas, %d archivos descargados, %d productos.",
        len(carpetas_nuevas),
        archivos_descargados,
        len(df_nuevo),
    )
    return {
        "carpetas": len(carpetas_nuevas),
        "carpetas_nuevas": len(carpetas_nuevas),
        "archivos": archivos_descargados,
        "productos": len(df_nuevo),
    }


__all__ = ["sincronizar_drive"]
