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

    from app.services.almacen.fuentes.google_drive_client import (
        buscar_o_crear_carpeta,
        mover_archivo,
        subir_archivo,
    )
    from app.services.almacen.extractor import leer_meta
    from app.services.almacen.apoyo import _folio_coincide_con_archivo

    dataframes: list[pd.DataFrame] = []
    archivos_descargados = 0
    with tempfile.TemporaryDirectory(prefix="flucito_drive_almacen_") as temporal:
        raiz = Path(temporal)
        for carpeta in carpetas_nuevas:
            logger.info("Procesando carpeta Drive: %s (id: %s)", carpeta.nombre, carpeta.id)
            destino = raiz / carpeta.id
            destino.mkdir(parents=True, exist_ok=True)
            rutas_xml: list[Path] = []
            archivo_by_name = {}
            for archivo in carpeta.archivos:
                ruta = destino / Path(archivo.nombre).name
                logger.info("  Descargando archivo: %s", archivo.nombre)
                descargar_archivo(cliente, archivo, ruta)
                archivos_descargados += 1
                if archivo.extension == ".xml":
                    rutas_xml.append(ruta)
                archivo_by_name[archivo.nombre] = archivo

            df_carpeta = []
            for ruta_xml in rutas_xml:
                logger.info("  Extrayendo datos de XML: %s", ruta_xml.name)
                df_xml = procesar_xml(str(ruta_xml), str(destino))
                if df_xml.empty:
                    continue
                df_carpeta.append(df_xml)

                # Obtener Proveedor y Fecha
                proveedor = str(df_xml["PROVEEDOR"].iloc[0]) if not df_xml["PROVEEDOR"].isna().all() else "Desconocido"
                fecha = str(df_xml["Fecha de última compra"].iloc[0]) if not df_xml["Fecha de última compra"].isna().all() else "SinFecha"
                nombre_subcarpeta = f"{proveedor} - {fecha}".replace("/", "-").replace("\\", "-")

                # Crear/buscar subcarpeta en Drive
                subcarpeta_id = buscar_o_crear_carpeta(cliente, nombre_subcarpeta, carpeta.id)

                # Determinar archivos a mover (XML + PDF/TXT asociados)
                archivos_a_mover = [ruta_xml.name]
                meta = leer_meta(str(ruta_xml))
                if meta["folio"] is not None and meta["year"]:
                    for arch_name in list(archivo_by_name.keys()):
                        ext = Path(arch_name).suffix.lower()
                        if ext in (".pdf", ".txt"):
                            ruta_apoyo = destino / Path(arch_name).name
                            if ruta_apoyo.exists() and _folio_coincide_con_archivo(str(ruta_apoyo), meta["folio"], rfc_proveedor=meta.get("rfc")):
                                archivos_a_mover.append(arch_name)

                # Mover archivos en Drive
                for nombre_arch in archivos_a_mover:
                    if nombre_arch in archivo_by_name:
                        arch_drive = archivo_by_name[nombre_arch]
                        mover_archivo(cliente, arch_drive.id, subcarpeta_id)
                        del archivo_by_name[nombre_arch]

                # Generar y subir Excel individual
                carpeta_mini = destino / "mini"
                carpeta_mini.mkdir(exist_ok=True)
                prefijo_mini = f"ENTRADAS_ALMACEN_{proveedor}_{carpeta.nombre}"
                guardar_en_base_acumulada(df_xml, str(carpeta_mini), limpiar_previos=True, prefijo=prefijo_mini)
                
                for f in carpeta_mini.iterdir():
                    if f.is_file():
                        subir_archivo(cliente, f, subcarpeta_id)
                        f.unlink()

            if df_carpeta:
                df_batch = pd.concat(df_carpeta, ignore_index=True)
                dataframes.append(df_batch)
                
                # Generar y subir Excel batch a la carpeta padre (ej. 25-09-2026)
                carpeta_batch = destino / "batch"
                carpeta_batch.mkdir(exist_ok=True)
                prefijo_batch = f"ENTRADAS_ALMACEN_{carpeta.nombre}"
                guardar_en_base_acumulada(df_batch, str(carpeta_batch), limpiar_previos=True, prefijo=prefijo_batch)
                
                for f in carpeta_batch.iterdir():
                    if f.is_file():
                        subir_archivo(cliente, f, carpeta.id)
                        f.unlink()

    if not dataframes:
        logger.warning("No se obtuvieron productos de las carpetas nuevas.")
        return {
            "carpetas": len(carpetas_nuevas),
            "carpetas_nuevas": len(carpetas_nuevas),
            "archivos": archivos_descargados,
            "productos": 0,
        }

    df_nuevo = pd.concat(dataframes, ignore_index=True)
    guardar_en_base_acumulada(df_nuevo, CARPETA_DATOS, limpiar_previos=True)
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
