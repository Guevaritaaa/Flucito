"""Genera archivos TXT de entradas de almacén para importación en Aspel SAE."""

from __future__ import annotations

import logging
import os
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

NOMBRE_TXT_COMAS = "BASE_ENTRADAS_ALMACEN_COMAS.txt"
NOMBRE_TXT_TABS = "BASE_ENTRADAS_ALMACEN_TABS.txt"


import csv

def generar_txt(df: pd.DataFrame, carpeta: str, separador: str, nombre: str) -> str:
    """Escribe DataFrame como TXT con separador dado. Devuelve ruta del archivo."""
    os.makedirs(carpeta, exist_ok=True)
    ruta = os.path.join(carpeta, nombre)
    
    # Copia para no alterar el df original
    df_export = df.copy()
    
    # 1. Rellenar campos vacíos (NaN) de bases viejas con 0
    df_export = df_export.fillna(0)
    
    # 2. Reemplazar comillas dobles, comas y saltos de línea explícitamente en todas las columnas de texto
    for col in df_export.columns:
        if df_export[col].dtype == 'object' or df_export[col].dtype == 'string':
            df_export[col] = df_export[col].astype(str)
            df_export[col] = df_export[col].str.replace('"', "'", regex=False)
            df_export[col] = df_export[col].str.replace(',', '', regex=False)
            df_export[col] = df_export[col].str.replace('\n', ' ', regex=False)

    
    df_export.to_csv(ruta, sep=separador, index=False, encoding="utf-8", quoting=csv.QUOTE_NONE, escapechar="\\")
    logger.info("TXT generado: %s (%d filas, separador: %s)", ruta, len(df_export), repr(separador))
    return ruta


def generar_ambos_txt(df: pd.DataFrame, carpeta: str, prefijo: str = "BASE_ENTRADAS_ALMACEN") -> dict[str, str]:
    """Genera versión con comas y con tabulaciones. Devuelve rutas."""
    ruta_comas = generar_txt(df, carpeta, ",", f"{prefijo}_COMAS.txt")
    ruta_tabs = generar_txt(df, carpeta, "\t", f"{prefijo}_TABS.txt")
    return {"comas": ruta_comas, "tabs": ruta_tabs}


__all__ = [
    "NOMBRE_TXT_COMAS",
    "NOMBRE_TXT_TABS",
    "generar_ambos_txt",
    "generar_txt",
]
