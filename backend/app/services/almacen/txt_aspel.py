"""Genera archivos TXT de entradas de almacén para importación en Aspel SAE."""

from __future__ import annotations

import logging
import os
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

NOMBRE_TXT_COMAS = "BASE_ENTRADAS_ALMACEN_COMAS.txt"
NOMBRE_TXT_TABS = "BASE_ENTRADAS_ALMACEN_TABS.txt"


def generar_txt(df: pd.DataFrame, carpeta: str, separador: str, nombre: str) -> str:
    """Escribe DataFrame como TXT con separador dado. Devuelve ruta del archivo."""
    os.makedirs(carpeta, exist_ok=True)
    ruta = os.path.join(carpeta, nombre)
    df.to_csv(ruta, sep=separador, index=False, encoding="utf-8")
    logger.info("TXT generado: %s (%d filas, separador: %s)", ruta, len(df), repr(separador))
    return ruta


def generar_ambos_txt(df: pd.DataFrame, carpeta: str) -> dict[str, str]:
    """Genera versión con comas y con tabulaciones. Devuelve rutas."""
    ruta_comas = generar_txt(df, carpeta, ",", NOMBRE_TXT_COMAS)
    ruta_tabs = generar_txt(df, carpeta, "\t", NOMBRE_TXT_TABS)
    return {"comas": ruta_comas, "tabs": ruta_tabs}


__all__ = [
    "NOMBRE_TXT_COMAS",
    "NOMBRE_TXT_TABS",
    "generar_ambos_txt",
    "generar_txt",
]
