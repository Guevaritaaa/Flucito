"""Sincroniza subcarpetas Drive con el pipeline local de almacén."""

from __future__ import annotations

import logging
import re
import tempfile
from pathlib import Path
from typing import Any

import pandas as pd

from app.core.config import settings
from app.services.almacen.apoyo import buscar_dato, obtener_apoyo_por_folio
from app.services.almacen.excel import (
    CARPETA_DATOS,
    NOMBRE_ARCHIVO_BASE,
    _buscar_decision_rollo,
    _precio_con_descuento,
    actualizar_precios_reporte_existente,
    guardar_en_base_acumulada,
    procesar_xml,
)
from app.services.almacen import extractor
from app.services.almacen.factores import (
    detectar_rollo_metros,
    formatear_menu_factores,
    guardar_factor_personalizado,
    recuperar_clave_truncada,
    resolver_linea,
)
from app.services.almacen.fuentes.google_drive import (
    MIME_CARPETA,
    DriveArchivo,
)
from app.services.almacen.fuentes.google_drive_client import (
    CARPETA_ENTRADAS_AL_INVENTARIO,
    CARPETA_REPORTES_HISTORICOS,
    PREFIJO_REPORTE,
    GoogleDriveConfigError,
    buscar_carpeta_hija,
    buscar_o_crear_carpeta,
    crear_cliente_drive,
    descargar_archivo,
    listar_carpetas_factura,
    normalizar_fecha_reporte,
)
from app.services.almacen.fuentes.estado_drive import (
    NOMBRE_ESTADO,
    cargar_estado,
    carpetas_con_novedades,
    guardar_estado,
    marcar_procesadas,
)
from app.services.almacen.fuentes.organizador import (
    construir_aviso_reubicacion_previa,
    reubicar_carpetas_mal_ubicadas,
)

logger = logging.getLogger(__name__)


def _nombre_drive_seguro(nombre: str) -> str:
    """Evita caracteres problemáticos al crear nombres de carpetas y reportes."""
    return re.sub(r'[\\/:*?"<>|]+', "-", nombre).strip() or "Desconocido"


def _concatenar_con_meta(dfs: list[pd.DataFrame]) -> pd.DataFrame:
    """Concatena DataFrames preservando el diccionario meta_por_clave en attrs."""
    meta_combinada: dict[str, dict[str, object]] = {}
    for df in dfs:
        if isinstance(df.attrs.get("meta_por_clave"), dict):
            meta_combinada.update(df.attrs["meta_por_clave"])
    combinado = pd.concat(dfs, ignore_index=True)
    combinado.attrs["meta_por_clave"] = meta_combinada
    return combinado


def inspeccionar_pendientes_carpeta(
    rutas_xml: list[Path],
    carpeta_local: Path,
    factores_elegidos: dict[str, str | None] | None = None,
    decisiones_rollos: dict[str, dict[str, object]] | None = None,
) -> dict[str, list[dict[str, object]]]:
    """Revisa qué líneas no tienen factor definido y qué rollos requieren confirmación."""
    lineas_sin_factor: dict[str, dict[str, object]] = {}
    rollos_pendientes: dict[str, dict[str, object]] = {}

    for ruta_xml in rutas_xml:
        try:
            conceptos = extractor.extraer_conceptos(str(ruta_xml))
            meta = extractor.leer_meta(str(ruta_xml))
        except Exception as error:
            logger.warning("No se pudo inspeccionar XML %s: %s", ruta_xml.name, error)
            continue

        apoyo = []
        if meta["folio"] is not None and meta["year"]:
            apoyo = obtener_apoyo_por_folio(
                str(carpeta_local),
                meta["year"],
                meta["folio"],
                rfc_proveedor=meta.get("rfc"),
            )

        datos = [
            buscar_dato(apoyo, c["no_identificacion"]) or buscar_dato(apoyo, c["codigo_secundario"])
            for c in conceptos
        ]
        if apoyo and all(d is None for d in datos) and len(apoyo) == len(conceptos):
            datos = apoyo

        for c, dato in zip(conceptos, datos):
            clave_apoyo = dato["clave_articulo"] if dato else None
            clave_xml = c.get("no_identificacion")
            clave_articulo = recuperar_clave_truncada(clave_apoyo, clave_xml) or clave_xml or ""
            descripcion_corta = (dato.get("descripcion_corta") if dato else None) or c["descripcion"]

            linea_raw = (dato["linea"] if dato else None) or ""
            if linea_raw:
                info_linea = resolver_linea(
                    linea_raw,
                    proveedor=str(c.get("proveedor_nombre") or ""),
                    descripcion=f"{c.get('descripcion') or ''} {descripcion_corta or ''}",
                    factores_temporales=factores_elegidos,
                )
                codigo_linea = str(info_linea["linea_resuelta"] or "")
                if codigo_linea and info_linea["factor"] is None:
                    lineas_sin_factor.setdefault(
                        codigo_linea,
                        {
                            "linea": codigo_linea,
                            "descripcion": info_linea["descripcion_linea"] or codigo_linea,
                        },
                    )

            info_rollo = detectar_rollo_metros(
                clave_unidad=c.get("clave_unidad"),
                descripcion_xml=str(c.get("descripcion") or ""),
                descripcion_apoyo=str(descripcion_corta or ""),
            )
            if info_rollo["requiere_confirmacion"]:
                decision = _buscar_decision_rollo(
                    decisiones_rollos,
                    clave_articulo,
                    clave_apoyo,
                    clave_xml,
                )
                falta_unidad = bool(info_rollo["es_xro"]) and "cambiar_a_mtr" not in decision
                falta_metros = (
                    info_rollo["metros"] is not None and "dividir_entre_metros" not in decision
                )
                if falta_unidad or falta_metros:
                    rollos_pendientes.setdefault(
                        clave_articulo,
                        {
                            "clave_articulo": clave_articulo,
                            "descripcion": c.get("descripcion") or descripcion_corta,
                            "clave_unidad": c.get("clave_unidad"),
                            "es_xro": bool(info_rollo["es_xro"]),
                            "metros": info_rollo["metros"],
                            "precio_compra_bruto": _precio_con_descuento(c),
                        },
                    )

    return {
        "lineas_sin_factor": list(lineas_sin_factor.values()),
        "rollos_pendientes": list(rollos_pendientes.values()),
    }


def construir_pregunta_interactiva(
    lineas_sin_factor: list[dict[str, object]],
    rollos_pendientes: list[dict[str, object]],
) -> str:
    """Construye el texto de pregunta para líneas sin factor y rollos/metros."""
    bloques: list[str] = []

    if lineas_sin_factor:
        for item in lineas_sin_factor:
            codigo = item["linea"]
            desc = item.get("descripcion") or ""
            etiqueta = f"{codigo} ({desc})" if desc and desc != codigo else str(codigo)
            bloques.append(
                f"La línea **{etiqueta}** no tiene factores de precios definidos. ¿Qué factor deseas aplicar?"
            )
        bloques.append(formatear_menu_factores())
        bloques.append(
            "¿Deseas guardar esta respuesta en el catálogo para futuras compras de esta línea? (**y/n**)"
        )

    if rollos_pendientes:
        for rollo in rollos_pendientes:
            clave = rollo["clave_articulo"]
            desc = rollo["descripcion"]
            es_xro = rollo["es_xro"]
            metros = rollo["metros"]
            precio = rollo["precio_compra_bruto"]
            if es_xro and metros:
                bloques.append(
                    f"Para el artículo **{clave}** (`{desc}`):\n"
                    f"- Viene con unidad **XRO** (rollo). ¿Deseas cambiar su `Clave unidad` de **XRO** a **MTR**? (**y/n**)\n"
                    f"- Se detectaron **{metros:g} metros** en la descripción. ¿Deseas dividir el `PRECIO COMPRA` (${precio:,.4f}) entre **{metros:g}** (`={precio}/{metros:g}`)? (**y/n**)"
                )
            elif es_xro:
                bloques.append(
                    f"El artículo **{clave}** (`{desc}`) viene con unidad **XRO** (rollo). "
                    "¿Deseas cambiar su `Clave unidad` de **XRO** a **MTR**? (**y/n**)"
                )
            elif metros:
                bloques.append(
                    f"Para el artículo **{clave}** (`{desc}`) se detectaron **{metros:g} metros**. "
                    f"¿Deseas dividir el `PRECIO COMPRA` (${precio:,.4f}) entre **{metros:g}** (`={precio}/{metros:g}`)? (**y/n**)"
                )

    return "\n\n".join(bloques)


def sincronizar_drive(
    cliente: Any | None = None,
    forzar: bool = False,
    interactivo: bool = False,
    confirmar_solo_xml: bool | None = None,
    omitir_incompletas: bool = False,
    factores_elegidos: dict[str, str | None] | None = None,
    guardar_factores: bool | None = None,
    decisiones_rollos: dict[str, dict[str, object]] | None = None,
) -> dict:
    """Descarga carpetas Drive temporalmente y actualiza base acumulada local."""
    logger.info("Iniciando sincronización con Google Drive...")
    cliente = cliente or crear_cliente_drive()
    carpeta_raiz_id = settings.google_drive_folder_id
    if not carpeta_raiz_id:
        raise GoogleDriveConfigError("Falta GOOGLE_DRIVE_FOLDER_ID")

    reubicacion = reubicar_carpetas_mal_ubicadas(cliente, carpeta_raiz_id)
    carpetas_reubicadas = reubicacion["carpetas_reubicadas"]
    archivos_reubicados_ids = set(reubicacion["archivos_reubicados_ids"])

    carpeta_entrada_id = buscar_carpeta_hija(
        cliente,
        CARPETA_ENTRADAS_AL_INVENTARIO,
        carpeta_raiz_id,
    )
    if not carpeta_entrada_id:
        logger.info("Drive: no existe la carpeta %s.", CARPETA_ENTRADAS_AL_INVENTARIO)
        return {
            "carpetas": 0,
            "archivos": 0,
            "productos": 0,
            "carpetas_reubicadas": carpetas_reubicadas,
        }

    carpetas = listar_carpetas_factura(cliente, carpeta_entrada_id)
    if not carpetas:
        logger.info("Drive: 0 carpetas encontradas en la carpeta raíz.")
        return {
            "carpetas": 0,
            "archivos": 0,
            "productos": 0,
            "carpetas_reubicadas": carpetas_reubicadas,
        }

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

    if carpetas_reubicadas or archivos_reubicados_ids:
        procesados = estado.setdefault("archivos", {})
        nombres_reubicados = {n.split("/")[0] for n in carpetas_reubicadas}
        for arch_id in archivos_reubicados_ids:
            procesados.pop(arch_id, None)
        for carpeta in carpetas:
            if carpeta.nombre in nombres_reubicados:
                for arch in carpeta.archivos:
                    procesados.pop(arch.id, None)

    carpetas_nuevas = carpetas_con_novedades(carpetas, estado)
    if not carpetas_nuevas:
        logger.info("Drive: Todas las carpetas están al día. 0 carpetas con novedades.")
        return {
            "carpetas": len(carpetas),
            "carpetas_nuevas": 0,
            "archivos": 0,
            "productos": 0,
            "carpetas_reubicadas": carpetas_reubicadas,
        }

    logger.info("Drive: %d carpeta(s) con archivos nuevos o modificados.", len(carpetas_nuevas))

    # 1. Verificar si alguna carpeta contiene únicamente archivos XML (sin TXT ni PDF de apoyo)
    carpetas_omitidas_solo_xml: list[str] = []
    if interactivo:
        carpetas_solo_xml = [
            c.nombre
            for c in carpetas_nuevas
            if any(a.extension == ".xml" for a in c.archivos)
            and not any(a.extension in (".pdf", ".txt") for a in c.archivos)
        ]
        if carpetas_solo_xml:
            if omitir_incompletas:
                carpetas_omitidas_solo_xml = list(carpetas_solo_xml)
                set_omitidas = set(carpetas_solo_xml)
                carpetas_nuevas = [
                    c for c in carpetas_nuevas if c.nombre not in set_omitidas
                ]
                if not carpetas_nuevas:
                    aviso_previo = (
                        construir_aviso_reubicacion_previa(carpetas_reubicadas)
                        if carpetas_reubicadas
                        else None
                    )
                    nombres_str = ", ".join(carpetas_omitidas_solo_xml)
                    mensaje_sin_completas = (
                        f"Se excluyeron las carpetas incompletas ({nombres_str}) porque solo contienen XML, "
                        "y no quedaron otras carpetas completas con TXT o PDF pendientes por procesar."
                    )
                    if aviso_previo:
                        mensaje_sin_completas = f"{aviso_previo}\n\n{mensaje_sin_completas}"
                    salida_sin_completas: dict[str, Any] = {
                        "carpetas": len(carpetas),
                        "carpetas_nuevas": 0,
                        "carpetas_procesadas": [],
                        "carpetas_omitidas_solo_xml": carpetas_omitidas_solo_xml,
                        "archivos": 0,
                        "productos": 0,
                        "carpetas_reubicadas": carpetas_reubicadas,
                        "cancelado_por_usuario": True,
                        "mensaje": mensaje_sin_completas,
                    }
                    if aviso_previo:
                        salida_sin_completas["advertencia_ubicacion"] = aviso_previo
                    return salida_sin_completas
            elif confirmar_solo_xml is False:
                aviso_previo = (
                    construir_aviso_reubicacion_previa(carpetas_reubicadas)
                    if carpetas_reubicadas
                    else None
                )
                mensaje_cancelacion = (
                    "Entendido, te sugiero revisar que hayas subido todos los documentos necesarios "
                    "(XML obligatorio, acompañado de su TXT o PDF de apoyo)."
                )
                if aviso_previo:
                    mensaje_cancelacion = f"{aviso_previo}\n\n{mensaje_cancelacion}"
                salida_cancelado: dict[str, Any] = {
                    "carpetas": len(carpetas_nuevas),
                    "carpetas_nuevas": len(carpetas_nuevas),
        "carpetas_procesadas": [c.nombre for c in carpetas_nuevas],
        "carpetas_omitidas_solo_xml": carpetas_omitidas_solo_xml,
                    "archivos": 0,
                    "productos": 0,
                    "carpetas_reubicadas": carpetas_reubicadas,
                    "cancelado_por_usuario": True,
                    "mensaje": mensaje_cancelacion,
                }
                if aviso_previo:
                    salida_cancelado["advertencia_ubicacion"] = aviso_previo
                return salida_cancelado
            elif False:
                return {
                    "carpetas": len(carpetas_nuevas),
                    "carpetas_nuevas": len(carpetas_nuevas),
        "carpetas_procesadas": [c.nombre for c in carpetas_nuevas],
        "carpetas_omitidas_solo_xml": carpetas_omitidas_solo_xml,
                    "archivos": 0,
                    "productos": 0,
                    "carpetas_reubicadas": carpetas_reubicadas,
                    "cancelado_por_usuario": True,
                    "mensaje": (
                        "Entendido, te sugiero revisar que hayas subido todos los documentos necesarios "
                        "(XML obligatorio, acompañado de su TXT o PDF de apoyo)."
                    ),
                }
            elif confirmar_solo_xml is None:
                aviso_previo = (
                    construir_aviso_reubicacion_previa(carpetas_reubicadas)
                    if carpetas_reubicadas
                    else None
                )
                nombres_str = ", ".join(carpetas_solo_xml)
                pregunta_base = (
                    f"Oye, la entrada **{nombres_str}** contiene solo archivos XML (sin TXT ni PDF de apoyo). "
                    "¿Olvidaste subirlos o no los tienes? Esto implica que el reporte no contendrá líneas ni "
                    "precios con factores. ¿Deseas generar el reporte solo con los XML proporcionados? (**y/n**)"
                )
                pregunta = (
                    f"{aviso_previo}\n\n{pregunta_base}"
                    if aviso_previo
                    else pregunta_base
                )
                salida_solo_xml: dict[str, Any] = {
                    "carpetas": len(carpetas_nuevas),
                    "carpetas_nuevas": len(carpetas_nuevas),
        "carpetas_procesadas": [c.nombre for c in carpetas_nuevas],
        "carpetas_omitidas_solo_xml": carpetas_omitidas_solo_xml,
                    "archivos": 0,
                    "productos": 0,
                    "carpetas_reubicadas": carpetas_reubicadas,
                    "requiere_confirmacion": True,
                    "tipo_confirmacion": "solo_xml",
                    "carpetas_solo_xml": carpetas_solo_xml,
                    "pregunta_usuario": pregunta,
                    "pregunta_sugerida": pregunta,
                }
                if aviso_previo:
                    salida_solo_xml["advertencia_ubicacion"] = aviso_previo
                return salida_solo_xml
            elif False:
                nombres_str = ", ".join(carpetas_solo_xml)
                pregunta = (
                    f"Oye, la entrada **{nombres_str}** contiene solo archivos XML (sin TXT ni PDF de apoyo). "
                    "¿Olvidaste subirlos o no los tienes? Esto implica que el reporte no contendrá líneas ni "
                    "precios con factores. ¿Deseas generar el reporte solo con los XML proporcionados? (**y/n**)"
                )
                return {
                    "carpetas": len(carpetas_nuevas),
                    "carpetas_nuevas": len(carpetas_nuevas),
        "carpetas_procesadas": [c.nombre for c in carpetas_nuevas],
        "carpetas_omitidas_solo_xml": carpetas_omitidas_solo_xml,
                    "archivos": 0,
                    "productos": 0,
                    "carpetas_reubicadas": carpetas_reubicadas,
                    "requiere_confirmacion": True,
                    "tipo_confirmacion": "solo_xml",
                    "carpetas_solo_xml": carpetas_solo_xml,
                    "pregunta_usuario": pregunta,
                    "pregunta_sugerida": pregunta,
                }

    # Guardar factores personalizados si el usuario confirmó guardarlos
    if guardar_factores and factores_elegidos:
        for linea_cod, factor_val in factores_elegidos.items():
            guardar_factor_personalizado(linea_cod, factor_val)

    from app.services.almacen.fuentes.google_drive_client import _listar_hijos, mover_archivo, subir_archivo, eliminar_archivo
    from app.services.almacen.apoyo import _folio_coincide_con_archivo

    dataframes: list[pd.DataFrame] = []
    archivos_descargados = 0
    with tempfile.TemporaryDirectory(prefix="flucito_drive_almacen_") as temporal:
        raiz = Path(temporal)
        descargas_por_carpeta: list[tuple[Any, Path, list[Path], dict[str, Any]]] = []

        # Fase A: Descargar todo al directorio temporal e inspeccionar antes de tocar Drive
        for carpeta in carpetas_nuevas:
            logger.info("Descargando carpeta Drive: %s (id: %s)", carpeta.nombre, carpeta.id)
            destino = raiz / carpeta.id
            destino.mkdir(parents=True, exist_ok=True)
            rutas_xml: list[Path] = []
            archivo_by_name: dict[str, Any] = {}
            for archivo in carpeta.archivos:
                ruta = destino / Path(archivo.nombre).name
                logger.info("  Descargando archivo: %s", archivo.nombre)
                descargar_archivo(cliente, archivo, ruta)
                archivos_descargados += 1
                if archivo.extension == ".xml":
                    rutas_xml.append(ruta)
                archivo_by_name[archivo.nombre] = archivo
            descargas_por_carpeta.append((carpeta, destino, rutas_xml, archivo_by_name))

        if interactivo:
            todas_lineas_sin_factor: dict[str, dict[str, object]] = {}
            todos_rollos_pendientes: dict[str, dict[str, object]] = {}
            for _carpeta, destino, rutas_xml, _archivo_by_name in descargas_por_carpeta:
                pendientes = inspeccionar_pendientes_carpeta(
                    rutas_xml,
                    destino,
                    factores_elegidos=factores_elegidos,
                    decisiones_rollos=decisiones_rollos,
                )
                for item_linea in pendientes["lineas_sin_factor"]:
                    todas_lineas_sin_factor.setdefault(str(item_linea["linea"]), item_linea)
                for item_rollo in pendientes["rollos_pendientes"]:
                    todos_rollos_pendientes.setdefault(str(item_rollo["clave_articulo"]), item_rollo)

            if todas_lineas_sin_factor or todos_rollos_pendientes:
                lista_lineas = list(todas_lineas_sin_factor.values())
                lista_rollos = list(todos_rollos_pendientes.values())
                if lista_lineas and lista_rollos:
                    tipo_conf = "factores_y_rollos"
                elif lista_lineas:
                    tipo_conf = "lineas_sin_factor"
                else:
                    tipo_conf = "rollos_pendientes"
                pregunta_base = construir_pregunta_interactiva(lista_lineas, lista_rollos)
                aviso_previo = (
                    construir_aviso_reubicacion_previa(carpetas_reubicadas)
                    if carpetas_reubicadas
                    else None
                )
                pregunta = (
                    f"{aviso_previo}\n\n{pregunta_base}"
                    if aviso_previo
                    else pregunta_base
                )
                salida_interactiva: dict[str, Any] = {
                    "carpetas": len(carpetas_nuevas),
                    "carpetas_nuevas": len(carpetas_nuevas),
        "carpetas_procesadas": [c.nombre for c in carpetas_nuevas],
        "carpetas_omitidas_solo_xml": carpetas_omitidas_solo_xml,
                    "archivos": archivos_descargados,
                    "productos": 0,
                    "carpetas_reubicadas": carpetas_reubicadas,
                    "requiere_confirmacion": True,
                    "tipo_confirmacion": tipo_conf,
                    "lineas_sin_factor": lista_lineas,
                    "rollos_pendientes": lista_rollos,
                    "menu_factores": formatear_menu_factores() if lista_lineas else None,
                    "pregunta_usuario": pregunta,
                    "pregunta_sugerida": pregunta,
                }
                if aviso_previo:
                    salida_interactiva["advertencia_ubicacion"] = aviso_previo
                return salida_interactiva
                return {
                    "carpetas": len(carpetas_nuevas),
                    "carpetas_nuevas": len(carpetas_nuevas),
        "carpetas_procesadas": [c.nombre for c in carpetas_nuevas],
        "carpetas_omitidas_solo_xml": carpetas_omitidas_solo_xml,
                    "archivos": archivos_descargados,
                    "productos": 0,
                    "carpetas_reubicadas": carpetas_reubicadas,
                    "requiere_confirmacion": True,
                    "tipo_confirmacion": tipo_conf,
                    "lineas_sin_factor": lista_lineas,
                    "rollos_pendientes": lista_rollos,
                    "menu_factores": formatear_menu_factores() if lista_lineas else None,
                    "pregunta_usuario": pregunta,
                    "pregunta_sugerida": pregunta,
                }

        # Fase B: Procesar XMLs, generar reportes y archivar en Google Drive
        carpeta_archivo_id = buscar_o_crear_carpeta(
            cliente,
            CARPETA_REPORTES_HISTORICOS,
            carpeta_raiz_id,
        )
        for carpeta, destino, rutas_xml, archivo_by_name in descargas_por_carpeta:
            carpeta_fecha_archivo_id = buscar_o_crear_carpeta(
                cliente,
                carpeta.nombre,
                carpeta_archivo_id,
            )
            df_carpeta: list[pd.DataFrame] = []
            fecha_carga = _nombre_drive_seguro(carpeta.nombre)

            # Agrupar por proveedor
            dfs_por_proveedor: dict[str, list[pd.DataFrame]] = {}
            archivos_por_proveedor: dict[str, list[str]] = {}

            for ruta_xml in rutas_xml:
                logger.info("  Extrayendo datos de XML: %s", ruta_xml.name)
                if factores_elegidos is None and decisiones_rollos is None:
                    df_xml = procesar_xml(str(ruta_xml), str(destino))
                else:
                    df_xml = procesar_xml(
                        str(ruta_xml),
                        str(destino),
                        factores_elegidos=factores_elegidos,
                        decisiones_rollos=decisiones_rollos,
                    )
                if df_xml.empty:
                    continue
                df_carpeta.append(df_xml)

                meta = extractor.leer_meta(str(ruta_xml))
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
                df_prov_concat = _concatenar_con_meta(dfs_prov)
                carpeta_mini = destino / "mini"
                carpeta_mini.mkdir(exist_ok=True)
                prefijo_mini = f"ENTRADAS_ALMACEN_{proveedor}_{fecha_carga}"

                guardar_en_base_acumulada(df_prov_concat, str(carpeta_mini), limpiar_previos=True, prefijo=prefijo_mini, guardar_resumen=False)

                for f in carpeta_mini.iterdir():
                    if f.is_file():
                        subir_archivo(cliente, f, subcarpeta_id)
                        f.unlink()

            if df_carpeta:
                df_batch = _concatenar_con_meta(df_carpeta)
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

            # Eliminar la carpeta original procesada si ya terminamos y no quedaron archivos huérfanos
            if not archivo_by_name:
                try:
                    eliminar_archivo(cliente, carpeta.id)
                    logger.info("Carpeta %s eliminada de ENTRADAS AL INVENTARIO tras procesar todos sus archivos.", carpeta.nombre)
                except Exception as e:
                    logger.warning(
                        "No se pudo eliminar la carpeta original %s (%s); reutilizándola como carpeta histórica.",
                        carpeta.nombre,
                        e,
                    )
                    try:
                        for item_arch in _listar_hijos(cliente, carpeta_fecha_archivo_id):
                            mover_archivo(cliente, item_arch["id"], carpeta.id)
                        eliminar_archivo(cliente, carpeta_fecha_archivo_id)
                        mover_archivo(cliente, carpeta.id, carpeta_archivo_id)
                    except Exception as e_fallback:
                        logger.warning("No se pudo reubicar la carpeta original %s: %s", carpeta.nombre, e_fallback)
            else:
                logger.warning("La carpeta %s no se eliminó porque quedaron %d archivos sin emparejar: %s", carpeta.nombre, len(archivo_by_name), list(archivo_by_name.keys()))

    if not dataframes:
        logger.warning("No se obtuvieron productos de las carpetas nuevas.")
        return {
            "carpetas": len(carpetas_nuevas),
            "carpetas_nuevas": len(carpetas_nuevas),
        "carpetas_procesadas": [c.nombre for c in carpetas_nuevas],
        "carpetas_omitidas_solo_xml": carpetas_omitidas_solo_xml,
            "archivos": archivos_descargados,
            "productos": 0,
            "carpetas_reubicadas": carpetas_reubicadas,
        }

    df_nuevo = _concatenar_con_meta(dataframes)
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
        "carpetas_procesadas": [c.nombre for c in carpetas_nuevas],
        "carpetas_omitidas_solo_xml": carpetas_omitidas_solo_xml,
        "archivos": archivos_descargados,
        "productos": len(df_nuevo),
        "carpetas_reubicadas": carpetas_reubicadas,
    }


def actualizar_precios_reportes_drive(
    cliente: Any | None = None,
    fecha: str | None = None,
    factores_elegidos: dict[str, str | None] | None = None,
) -> dict[str, object]:
    """Revisa los reportes ya generados (en DOCUMENTOS ENTRADA de Drive y la base local)
    y si detecta que no tienen los precios o fórmulas aplicadas, se los calcula y actualiza.
    """
    from app.services.almacen.fuentes.google_drive_client import (
        _listar_hijos,
        eliminar_archivo,
        subir_archivo,
    )

    reportes_revisados = 0
    reportes_actualizados: list[str] = []
    filas_actualizadas_total = 0
    base_local_actualizada = False

    with tempfile.TemporaryDirectory(prefix="flucito_precios_reportes_") as temporal:
        raiz_temp = Path(temporal)
        dir_apoyo_global = raiz_temp / "apoyo_global"
        dir_apoyo_global.mkdir(parents=True, exist_ok=True)

        # Copiar archivos de apoyo locales si existen en CARPETA_DATOS
        carpeta_datos_path = Path(CARPETA_DATOS)
        if carpeta_datos_path.is_dir():
            for arch_local in carpeta_datos_path.iterdir():
                if (
                    arch_local.is_file()
                    and arch_local.suffix.lower() in (".xml", ".pdf", ".txt")
                    and not arch_local.name.upper().startswith(PREFIJO_REPORTE)
                    and not arch_local.name.upper().startswith("BASE_ENTRADAS_ALMACEN")
                ):
                    (dir_apoyo_global / arch_local.name).write_bytes(arch_local.read_bytes())

        # 1. Revisar reportes históricos en Google Drive (DOCUMENTOS ENTRADA)
        try:
            carpeta_raiz_id = settings.google_drive_folder_id
            if cliente is not None or carpeta_raiz_id:
                cliente = cliente or crear_cliente_drive()
                if carpeta_raiz_id:
                    fecha_filtro = normalizar_fecha_reporte(fecha) if fecha else None
                    carpetas_archivo = [
                        elem
                        for elem in _listar_hijos(cliente, carpeta_raiz_id)
                        if elem.get("mimeType") == MIME_CARPETA
                        and elem.get("name") == CARPETA_REPORTES_HISTORICOS
                    ]

                    for carpeta_archivo in carpetas_archivo:
                        carpetas_fecha = [
                            elem
                            for elem in _listar_hijos(cliente, carpeta_archivo["id"])
                            if elem.get("mimeType") == MIME_CARPETA
                            and (fecha_filtro is None or elem.get("name") == fecha_filtro)
                        ]

                        for idx_f, carpeta_fecha in enumerate(carpetas_fecha):
                            dir_fecha = raiz_temp / f"fecha_{idx_f}"
                            dir_apoyo_fecha = dir_fecha / "apoyo"
                            dir_apoyo_fecha.mkdir(parents=True, exist_ok=True)

                            # Recolectar subcarpetas y la carpeta de fecha (subcarpetas primero para reunir XML/TXT/PDF)
                            nodos_carpeta: list[tuple[str, str, list[dict]]] = []
                            cola = [(carpeta_fecha["id"], carpeta_fecha.get("name", ""))]
                            visitadas: set[str] = set()
                            while cola:
                                cid, cnombre = cola.pop(0)
                                if cid in visitadas:
                                    continue
                                visitadas.add(cid)
                                hijos = _listar_hijos(cliente, cid)
                                nodos_carpeta.append((cid, cnombre, hijos))
                                for h in hijos:
                                    if h.get("mimeType") == MIME_CARPETA:
                                        cola.append((h["id"], h.get("name", "")))

                            # Procesar de abajo hacia arriba (subcarpetas de proveedor antes que carpeta de fecha)
                            for idx_c, (cid, _cnombre, hijos) in enumerate(reversed(nodos_carpeta)):
                                archivos_hijos = [
                                    h for h in hijos if h.get("mimeType") != MIME_CARPETA
                                ]
                                por_nombre = {h.get("name", ""): h for h in archivos_hijos}

                                # Descargar archivos de apoyo (.xml, .pdf, .txt de factura) si hay
                                for h in archivos_hijos:
                                    nombre_h = h.get("name", "")
                                    ext_h = Path(nombre_h).suffix.lower()
                                    if (
                                        ext_h in (".xml", ".pdf", ".txt")
                                        and not nombre_h.upper().startswith(PREFIJO_REPORTE)
                                    ):
                                        destino_apoyo = dir_apoyo_fecha / Path(nombre_h).name
                                        if not destino_apoyo.exists():
                                            arch_obj = DriveArchivo(
                                                id=h["id"],
                                                nombre=nombre_h,
                                                mime_type=h.get("mimeType", ""),
                                                modificado=h.get("modifiedTime", ""),
                                                carpeta_id=cid,
                                            )
                                            descargar_archivo(cliente, arch_obj, destino_apoyo)
                                            (dir_apoyo_global / destino_apoyo.name).write_bytes(
                                                destino_apoyo.read_bytes()
                                            )

                                # Revisar reportes .xlsx en esta carpeta
                                reportes_xlsx = [
                                    h
                                    for h in archivos_hijos
                                    if Path(h.get("name", "")).suffix.lower() == ".xlsx"
                                    and h.get("name", "").upper().startswith(PREFIJO_REPORTE)
                                ]
                                for idx_r, rep in enumerate(reportes_xlsx):
                                    nombre_xlsx = rep["name"]
                                    prefijo_rep = Path(nombre_xlsx).stem
                                    dir_rep = dir_fecha / f"rep_{idx_c}_{idx_r}"
                                    dir_rep.mkdir(parents=True, exist_ok=True)
                                    ruta_xlsx_local = dir_rep / nombre_xlsx

                                    arch_xlsx = DriveArchivo(
                                        id=rep["id"],
                                        nombre=nombre_xlsx,
                                        mime_type=rep.get("mimeType", ""),
                                        modificado=rep.get("modifiedTime", ""),
                                        carpeta_id=cid,
                                    )
                                    descargar_archivo(cliente, arch_xlsx, ruta_xlsx_local)
                                    tiene_txts_drive = (
                                        f"{prefijo_rep}_COMAS.txt" in por_nombre
                                        and f"{prefijo_rep}_TABS.txt" in por_nombre
                                    )

                                    res_rep = actualizar_precios_reporte_existente(
                                        str(ruta_xlsx_local),
                                        carpeta_apoyo=str(dir_apoyo_fecha),
                                        factores_elegidos=factores_elegidos,
                                        actualizar_resumen=False,
                                        generar_txt_si_faltan=not tiene_txts_drive,
                                    )
                                    reportes_revisados += 1
                                    if res_rep.get("actualizado"):
                                        reportes_actualizados.append(nombre_xlsx)
                                        filas_actualizadas_total += int(
                                            res_rep.get("filas_actualizadas", 0)
                                        )
                                        for arch_subir in (
                                            ruta_xlsx_local,
                                            dir_rep / f"{prefijo_rep}_COMAS.txt",
                                            dir_rep / f"{prefijo_rep}_TABS.txt",
                                        ):
                                            if arch_subir.is_file():
                                                existente = por_nombre.get(arch_subir.name)
                                                if existente:
                                                    eliminar_archivo(cliente, existente["id"])
                                                subir_archivo(cliente, arch_subir, cid)
        except GoogleDriveConfigError as error:
            logger.info("Drive no disponible al actualizar precios de reportes: %s", error)
        except Exception as error:
            logger.warning("No se pudieron revisar reportes en Drive: %s", error)

        # 2. Revisar reporte base local (BASE_ENTRADAS_ALMACEN.xlsx)
        ruta_base_local = Path(CARPETA_DATOS) / NOMBRE_ARCHIVO_BASE
        if ruta_base_local.is_file():
            res_local = actualizar_precios_reporte_existente(
                str(ruta_base_local),
                carpeta_apoyo=str(dir_apoyo_global),
                factores_elegidos=factores_elegidos,
                actualizar_resumen=True,
                generar_txt_si_faltan=True,
            )
            reportes_revisados += 1
            if res_local.get("actualizado"):
                base_local_actualizada = True
                reportes_actualizados.append(NOMBRE_ARCHIVO_BASE)
                filas_actualizadas_total += int(res_local.get("filas_actualizadas", 0))

    return {
        "reportes_revisados": reportes_revisados,
        "reportes_actualizados": reportes_actualizados,
        "total_actualizados": len(reportes_actualizados),
        "filas_actualizadas": filas_actualizadas_total,
        "base_local_actualizada": base_local_actualizada,
    }


__all__ = [
    "actualizar_precios_reportes_drive",
    "construir_pregunta_interactiva",
    "inspeccionar_pendientes_carpeta",
    "sincronizar_drive",
]
