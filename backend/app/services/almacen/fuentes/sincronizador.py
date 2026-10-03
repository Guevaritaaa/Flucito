"""Sincroniza subcarpetas Drive con el pipeline local de almacén."""

from __future__ import annotations

import logging
import re
import tempfile
from pathlib import Path
from typing import Any

import pandas as pd

from app.core.config import settings
from app.services.almacen.excel import (
    CARPETA_DATOS,
    NOMBRE_ARCHIVO_BASE,
    guardar_en_base_acumulada,
    procesar_xml,
)
from app.services.almacen.fuentes.google_drive_client import (
    CARPETA_ENTRADAS_AL_INVENTARIO,
    CARPETA_REPORTES_HISTORICOS,
    GoogleDriveConfigError,
    buscar_carpeta_hija,
    buscar_o_crear_carpeta,
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


def _nombre_drive_seguro(nombre: str) -> str:
    """Evita caracteres problemáticos al crear nombres de carpetas y reportes."""
    return re.sub(r'[\\/:*?"<>|]+', "-", nombre).strip() or "Desconocido"


def sincronizar_drive(cliente: Any | None = None, forzar: bool = False) -> dict:
    """Descarga carpetas Drive temporalmente y actualiza base acumulada local."""
    logger.info("Iniciando sincronización con Google Drive...")
    cliente = cliente or crear_cliente_drive()
    carpeta_raiz_id = settings.google_drive_folder_id
    if not carpeta_raiz_id:
        raise GoogleDriveConfigError("Falta GOOGLE_DRIVE_FOLDER_ID")

    carpeta_entrada_id = buscar_carpeta_hija(
        cliente,
        CARPETA_ENTRADAS_AL_INVENTARIO,
        carpeta_raiz_id,
    )
    if not carpeta_entrada_id:
        logger.info("Drive: no existe la carpeta %s.", CARPETA_ENTRADAS_AL_INVENTARIO)
        return {"carpetas": 0, "archivos": 0, "productos": 0}

    carpetas = listar_carpetas_factura(cliente, carpeta_entrada_id)
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

    from app.services.almacen.fuentes.google_drive_client import mover_archivo, subir_archivo, eliminar_archivo
    from app.services.almacen.extractor import leer_meta
    from app.services.almacen.apoyo import _folio_coincide_con_archivo

    dataframes: list[pd.DataFrame] = []
    archivos_descargados = 0
    carpeta_archivo_id = buscar_o_crear_carpeta(
        cliente,
        CARPETA_REPORTES_HISTORICOS,
        carpeta_raiz_id,
    )
    with tempfile.TemporaryDirectory(prefix="flucito_drive_almacen_") as temporal:
        raiz = Path(temporal)
        for carpeta in carpetas_nuevas:
            logger.info("Procesando carpeta Drive: %s (id: %s)", carpeta.nombre, carpeta.id)
            carpeta_fecha_archivo_id = buscar_o_crear_carpeta(
                cliente,
                carpeta.nombre,
                carpeta_archivo_id,
            )
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
            fecha_carga = _nombre_drive_seguro(carpeta.nombre)
            
            # Agrupar por proveedor
            dfs_por_proveedor = {}
            archivos_por_proveedor = {}
            
            for ruta_xml in rutas_xml:
                logger.info("  Extrayendo datos de XML: %s", ruta_xml.name)
                df_xml = procesar_xml(str(ruta_xml), str(destino))
                if df_xml.empty:
                    continue
                df_carpeta.append(df_xml)

                meta = leer_meta(str(ruta_xml))
                proveedor = _nombre_drive_seguro(meta.get("proveedor_nombre") or "Proveedor desconocido")
                
                if proveedor not in dfs_por_proveedor:
                    dfs_por_proveedor[proveedor] = []
                    archivos_por_proveedor[proveedor] = []
                
                dfs_por_proveedor[proveedor].append(df_xml)

                # Determinar archivos a mover (XML + PDF/TXT asociados)
                archivos_a_mover = [ruta_xml.name]
                if meta["folio"] is not None and meta["year"]:
                    for arch_name in list(archivo_by_name.keys()):
                        ext = Path(arch_name).suffix.lower()
                        if ext in (".pdf", ".txt"):
                            ruta_apoyo = destino / Path(arch_name).name
                            if ruta_apoyo.exists() and _folio_coincide_con_archivo(str(ruta_apoyo), meta["folio"], rfc_proveedor=meta.get("rfc")):
                                archivos_a_mover.append(arch_name)

                archivos_por_proveedor[proveedor].extend(archivos_a_mover)

            # Procesar por proveedor
            for proveedor, dfs_prov in dfs_por_proveedor.items():
                nombre_subcarpeta = f"{proveedor} - {fecha_carga}"
                subcarpeta_id = buscar_o_crear_carpeta(
                    cliente,
                    nombre_subcarpeta,
                    carpeta_fecha_archivo_id,
                )

                # Mover archivos en Drive
                for nombre_arch in archivos_por_proveedor[proveedor]:
                    if nombre_arch in archivo_by_name:
                        arch_drive = archivo_by_name[nombre_arch]
                        mover_archivo(cliente, arch_drive.id, subcarpeta_id)
                        del archivo_by_name[nombre_arch]

                # Generar y subir Excel unificado por proveedor (sin JSON)
                df_prov_concat = pd.concat(dfs_prov, ignore_index=True)
                carpeta_mini = destino / "mini"
                carpeta_mini.mkdir(exist_ok=True)
                prefijo_mini = f"ENTRADAS_ALMACEN_{proveedor}_{fecha_carga}"
                
                guardar_en_base_acumulada(df_prov_concat, str(carpeta_mini), limpiar_previos=True, prefijo=prefijo_mini, guardar_resumen=False)
                
                for f in carpeta_mini.iterdir():
                    if f.is_file():
                        subir_archivo(cliente, f, subcarpeta_id)
                        f.unlink()

            if df_carpeta:
                df_batch = pd.concat(df_carpeta, ignore_index=True)
                dataframes.append(df_batch)
                
                # Guarda el Excel acumulado de la carga en la carpeta de archivo por fecha.
                carpeta_batch = destino / "batch"
                carpeta_batch.mkdir(exist_ok=True)
                prefijo_batch = f"ENTRADAS_ALMACEN_{fecha_carga}"
                # Sin JSON tampoco para el reporte batch de drive
                guardar_en_base_acumulada(df_batch, str(carpeta_batch), limpiar_previos=True, prefijo=prefijo_batch, guardar_resumen=False)
                
                for f in carpeta_batch.iterdir():
                    if f.is_file():
                        subir_archivo(cliente, f, carpeta_fecha_archivo_id)
                        f.unlink()

            # Eliminar la carpeta original procesada si ya terminamos
            try:
                eliminar_archivo(cliente, carpeta.id)
                logger.info("Carpeta %s eliminada de ENTRADAS AL INVENTARIO tras procesar.", carpeta.nombre)
            except Exception as e:
                logger.warning("No se pudo eliminar la carpeta original %s: %s", carpeta.nombre, e)

    if not dataframes:
        logger.warning("No se obtuvieron productos de las carpetas nuevas.")
        return {
            "carpetas": len(carpetas_nuevas),
            "carpetas_nuevas": len(carpetas_nuevas),
            "archivos": archivos_descargados,
            "productos": 0,
        }

    df_nuevo = pd.concat(dataframes, ignore_index=True)
    guardar_en_base_acumulada(df_nuevo, str(CARPETA_DATOS), limpiar_previos=True)
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
