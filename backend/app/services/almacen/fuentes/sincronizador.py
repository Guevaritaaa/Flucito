"""Sincroniza subcarpetas Drive con el pipeline local de almacén."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import pandas as pd

from app.services.almacen.excel import (
    CARPETA_DATOS,
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


def sincronizar_drive(cliente: Any | None = None) -> dict:
    """Descarga carpetas Drive temporalmente y actualiza base acumulada local."""
    cliente = cliente or crear_cliente_drive()
    carpetas = listar_carpetas_factura(cliente)
    if not carpetas:
        return {"carpetas": 0, "archivos": 0, "productos": 0}

    ruta_estado = Path(CARPETA_DATOS) / NOMBRE_ESTADO
    estado = cargar_estado(ruta_estado)
    carpetas_nuevas = carpetas_con_novedades(carpetas, estado)
    if not carpetas_nuevas:
        return {
            "carpetas": len(carpetas),
            "carpetas_nuevas": 0,
            "archivos": 0,
            "productos": 0,
        }

    dataframes: list[pd.DataFrame] = []
    archivos_descargados = 0
    with tempfile.TemporaryDirectory(prefix="flucito_drive_almacen_") as temporal:
        raiz = Path(temporal)
        for carpeta in carpetas_nuevas:
            destino = raiz / carpeta.id
            destino.mkdir(parents=True, exist_ok=True)
            rutas_xml: list[Path] = []
            for archivo in carpeta.archivos:
                ruta = destino / Path(archivo.nombre).name
                descargar_archivo(cliente, archivo, ruta)
                archivos_descargados += 1
                if archivo.extension == ".xml":
                    rutas_xml.append(ruta)

            for ruta_xml in rutas_xml:
                dataframes.append(procesar_xml(str(ruta_xml), str(destino)))

    if not dataframes:
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
    return {
        "carpetas": len(carpetas_nuevas),
        "carpetas_nuevas": len(carpetas_nuevas),
        "archivos": archivos_descargados,
        "productos": len(df_nuevo),
    }


__all__ = ["sincronizar_drive"]
