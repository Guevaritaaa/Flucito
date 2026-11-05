"""Inspección, reubicación inteligente y organización de carpetas en Google Drive."""

from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.services.almacen.excel import CARPETA_DATOS
from app.services.almacen.fuentes.estado_drive import (
    NOMBRE_ESTADO,
    cargar_estado,
    guardar_estado,
)
from app.services.almacen.fuentes.google_drive import MIME_CARPETA
from app.services.almacen.fuentes.google_drive_client import (
    CARPETA_ENTRADAS_AL_INVENTARIO,
    CARPETA_REPORTES_HISTORICOS,
    PREFIJO_REPORTE,
    GoogleDriveConfigError,
    _listar_hijos,
    buscar_carpeta_hija,
    buscar_o_crear_carpeta,
    crear_cliente_drive,
    eliminar_archivo,
    extraer_anio_mes_de_fecha_carpeta,
    listar_carpetas_fecha_en_historico,
    mover_archivo,
    obtener_o_crear_carpeta_mes_historico,
)

logger = logging.getLogger(__name__)

PATRON_FECHA_NOMBRE = re.compile(r"(\d{2}-\d{2}-\d{4})")


PREFIJO_CARPETA_ARCHIVOS_SUELTOS = "ARCHIVOS_SUELTOS_"


def _eliminar_archivo_seguro(cliente: Any, archivo_id: str) -> bool:
    """Intenta eliminar un archivo/carpeta en Drive sin abortar si la cuenta de servicio recibe 403."""
    try:
        eliminar_archivo(cliente, archivo_id)
        return True
    except Exception as exc:
        logger.warning("No se pudo eliminar elemento %s en Drive (permisos): %s", archivo_id, exc)
        return False


def _es_nombre_fecha_pura(nombre: str) -> bool:
    """Indica si el nombre de la carpeta es exactamente una fecha DD-MM-YYYY (ej. '30-10-2026')."""
    return bool(PATRON_FECHA_NOMBRE.fullmatch((nombre or "").strip()))


def es_carpeta_archivos_sueltos(nombre: str) -> bool:
    """Indica si el nombre corresponde a una carpeta de revisión manual de archivos sueltos."""
    return nombre.upper().startswith(PREFIJO_CARPETA_ARCHIVOS_SUELTOS)


def es_reporte_excel(nombre: str) -> bool:
    """Indica si el archivo es un reporte Excel generado (ENTRADAS_ALMACEN_*.xlsx)."""
    return (
        Path(nombre).suffix.lower() == ".xlsx"
        and nombre.upper().startswith(PREFIJO_REPORTE)
    )


def es_archivo_generado(nombre: str) -> bool:
    """Indica si el archivo fue generado por Flucito (Excel, TXT o JSON de salida)."""
    nombre_upper = nombre.upper()
    return nombre_upper.startswith(PREFIJO_REPORTE) or nombre_upper.startswith(
        "BASE_ENTRADAS_ALMACEN"
    )


def es_xml_o_txt_entrada(nombre: str) -> bool:
    """Indica si es un documento XML o TXT de entrada (no generado por el sistema)."""
    ext = Path(nombre).suffix.lower()
    return ext in {".xml", ".txt"} and not es_archivo_generado(nombre)


def es_documento_entrada(nombre: str) -> bool:
    """Indica si es un documento XML, PDF o TXT de entrada (no generado por el sistema)."""
    ext = Path(nombre).suffix.lower()
    return ext in {".xml", ".txt", ".pdf"} and not es_archivo_generado(nombre)


def construir_aviso_reubicacion_previa(carpetas: list[str]) -> str:
    """Construye el aviso cuando se reubican carpetas antes de pedir confirmación o cancelar."""
    lista = ", ".join(carpetas)
    return (
        f"Por cierto, detecté que las carpetas **{lista}** no tenían su reporte generado "
        "y estaban dentro de **DOCUMENTOS ENTRADA** (o anidadas en otra carpeta), así que las moví automáticamente a "
        "**ENTRADAS AL INVENTARIO** para poder procesarlas.\n\n"
        "⚠️ **Aviso:** Recuerda que las facturas pendientes (XML, PDF o TXT) deben subirse "
        "siempre en su propia carpeta por fecha dentro de **ENTRADAS AL INVENTARIO** en Google Drive."
    )


def construir_advertencia_ubicacion(carpetas: list[str]) -> str:
    """Construye el mensaje de advertencia cuando se detectan carpetas mal ubicadas."""
    lista = ", ".join(carpetas)
    return (
        f"He detectado que las carpetas {lista} estaban mal ubicadas dentro de "
        "**DOCUMENTOS ENTRADA** (o anidadas dentro de otra carpeta). Primero las moví a **ENTRADAS AL INVENTARIO** y "
        "generé todos sus reportes con éxito.\n\n"
        "⚠️ **Aviso:** Recuerda que para subir documentos a procesar, deben colocarse "
        "en la carpeta **ENTRADAS AL INVENTARIO** en Google Drive."
    )


def construir_advertencia_archivos_sueltos(
    archivos: list[str],
    nombre_carpeta: str,
) -> str:
    """Construye el mensaje de aviso cuando se encuentran archivos sueltos para intervención manual."""
    lista = ", ".join(archivos)
    return (
        f"Se encontraron estos archivos sueltos: {lista}. "
        f"Por favor revisa la carpeta **{nombre_carpeta}** y organiza manualmente los archivos."
    )


def _contar_documentos_entrada(archivos: list[dict]) -> dict[str, int]:
    """Cuenta XML, TXT y PDF de entrada dentro de una lista de archivos de Drive."""
    xmls = 0
    txts = 0
    pdfs = 0
    for archivo in archivos:
        if archivo.get("mimeType") == MIME_CARPETA:
            continue
        nombre = archivo.get("name", "")
        if es_archivo_generado(nombre):
            continue
        ext = Path(nombre).suffix.lower()
        if ext == ".xml":
            xmls += 1
        elif ext == ".txt":
            txts += 1
        elif ext == ".pdf":
            pdfs += 1
    return {"xmls": xmls, "txts": txts, "pdfs": pdfs}


def _mover_contenido_carpeta(
    cliente: Any,
    origen_id: str,
    destino_id: str,
    hijos_origen: list[dict] | None = None,
) -> list[str]:
    """Mueve todos los elementos de una carpeta origen a una carpeta destino y elimina origen."""
    elementos = hijos_origen if hijos_origen is not None else _listar_hijos(cliente, origen_id)
    archivos_movidos_ids: list[str] = []

    for item in elementos:
        item_id = item["id"]
        item_nombre = item.get("name", "")
        if item.get("mimeType") == MIME_CARPETA:
            sub_destino_id = buscar_carpeta_hija(cliente, item_nombre, destino_id)
            if sub_destino_id:
                archivos_movidos_ids.extend(
                    _mover_contenido_carpeta(cliente, item_id, sub_destino_id)
                )
            else:
                mover_archivo(cliente, item_id, destino_id)
        else:
            mover_archivo(cliente, item_id, destino_id)
            archivos_movidos_ids.append(item_id)

    _eliminar_archivo_seguro(cliente, origen_id)
    return archivos_movidos_ids


def reubicar_carpetas_mal_ubicadas(
    cliente: Any | None = None,
    carpeta_raiz_id: str | None = None,
) -> dict[str, Any]:
    """Detecta carpetas en DOCUMENTOS ENTRADA (o subcarpetas anidadas en ENTRADAS AL INVENTARIO) con XML/TXT pero sin Excel y las mueve a ENTRADAS AL INVENTARIO."""
    cliente = cliente or crear_cliente_drive()
    root_id = carpeta_raiz_id or settings.google_drive_folder_id
    if not root_id:
        raise GoogleDriveConfigError("Falta GOOGLE_DRIVE_FOLDER_ID")

    carpetas_reubicadas: list[str] = []
    archivos_reubicados_ids: list[str] = []
    carpeta_entrada_id: str | None = None

    try:
        carpeta_historico_id = buscar_carpeta_hija(
            cliente,
            CARPETA_REPORTES_HISTORICOS,
            root_id,
        )
    except AttributeError:
        # Soporte para mocks simples en pruebas unitarias sin métodos de API Drive
        return {"carpetas_reubicadas": [], "archivos_reubicados_ids": []}

    def obtener_carpeta_entrada() -> str:
        nonlocal carpeta_entrada_id
        if not carpeta_entrada_id:
            carpeta_entrada_id = buscar_o_crear_carpeta(
                cliente,
                CARPETA_ENTRADAS_AL_INVENTARIO,
                root_id,
            )
        return carpeta_entrada_id

    # Paso 0: Revisar si en ENTRADAS AL INVENTARIO hay subcarpetas anidadas (ej. 30-10-2026 dentro de 20-10-2026)
    carpeta_entrada_existente = buscar_carpeta_hija(
        cliente,
        CARPETA_ENTRADAS_AL_INVENTARIO,
        root_id,
    )
    if carpeta_entrada_existente:
        carpeta_entrada_id = carpeta_entrada_existente
        items_entrada = _listar_hijos(cliente, carpeta_entrada_existente)
        carpetas_en_entrada = [
            item
            for item in items_entrada
            if item.get("mimeType") == MIME_CARPETA
            and not es_carpeta_archivos_sueltos(item.get("name", ""))
        ]
        for carp_ent in carpetas_en_entrada:
            carp_ent_id = carp_ent["id"]
            carp_ent_nombre = carp_ent.get("name", carp_ent_id)
            hijos_ent = _listar_hijos(cliente, carp_ent_id)
            subs_ent = [h for h in hijos_ent if h.get("mimeType") == MIME_CARPETA]
            for sub_ent in subs_ent:
                sub_id = sub_ent["id"]
                sub_nombre = sub_ent.get("name", sub_id)
                hijos_sub = _listar_hijos(cliente, sub_id)
                archivos_sub = [a for a in hijos_sub if a.get("mimeType") != MIME_CARPETA]
                sub_tiene_xml_txt = any(es_xml_o_txt_entrada(a.get("name", "")) for a in archivos_sub)
                sub_tiene_reporte = any(es_reporte_excel(a.get("name", "")) for a in archivos_sub)
                if not sub_tiene_xml_txt or sub_tiene_reporte:
                    continue

                if _es_nombre_fecha_pura(sub_nombre):
                    # Es una carpeta de fecha (ej. 30-10-2026) metida dentro de otra carpeta (ej. 20-10-2026)
                    existente_top_id = buscar_carpeta_hija(cliente, sub_nombre, carpeta_entrada_existente)
                    if existente_top_id and existente_top_id != sub_id:
                        for arch in archivos_sub:
                            if es_documento_entrada(arch.get("name", "")):
                                mover_archivo(cliente, arch["id"], existente_top_id, carpeta_origen_id=sub_id)
                                archivos_reubicados_ids.append(arch["id"])
                        _eliminar_archivo_seguro(cliente, sub_id)
                    else:
                        mover_archivo(cliente, sub_id, carpeta_entrada_existente, carpeta_origen_id=carp_ent_id)
                        archivos_reubicados_ids.extend(a["id"] for a in archivos_sub)
                    if sub_nombre not in carpetas_reubicadas:
                        carpetas_reubicadas.append(sub_nombre)
                    logger.info(
                        "Subcarpeta de fecha '%s/%s' desanidada hacia %s/%s.",
                        carp_ent_nombre,
                        sub_nombre,
                        CARPETA_ENTRADAS_AL_INVENTARIO,
                        sub_nombre,
                    )
                else:
                    # Subcarpeta común dentro de una carpeta de fecha en ENTRADAS AL INVENTARIO: subir archivos al nivel de la carpeta de fecha
                    for arch in archivos_sub:
                        if es_documento_entrada(arch.get("name", "")):
                            mover_archivo(cliente, arch["id"], carp_ent_id, carpeta_origen_id=sub_id)
                            archivos_reubicados_ids.append(arch["id"])
                    _eliminar_archivo_seguro(cliente, sub_id)
                    etiqueta = f"{carp_ent_nombre}/{sub_nombre}"
                    if etiqueta not in carpetas_reubicadas:
                        carpetas_reubicadas.append(etiqueta)

    if not carpeta_historico_id:
        return {
            "carpetas_reubicadas": carpetas_reubicadas,
            "archivos_reubicados_ids": archivos_reubicados_ids,
        }

    carpetas_historico = listar_carpetas_fecha_en_historico(
        cliente,
        carpeta_historico_id,
        fn_listar_hijos=_listar_hijos,
    )

    for carpeta in carpetas_historico:
        carpeta_id = carpeta["id"]
        carpeta_nombre = carpeta.get("name", carpeta_id)
        hijos = _listar_hijos(cliente, carpeta_id)

        archivos_directos = [h for h in hijos if h.get("mimeType") != MIME_CARPETA]
        subcarpetas = [h for h in hijos if h.get("mimeType") == MIME_CARPETA]

        tiene_xml_txt_directo = any(
            es_xml_o_txt_entrada(a.get("name", "")) for a in archivos_directos
        )
        tiene_reporte_directo = any(
            es_reporte_excel(a.get("name", "")) for a in archivos_directos
        )

        info_subcarpetas = []
        for sub in subcarpetas:
            hijos_sub = _listar_hijos(cliente, sub["id"])
            archivos_sub = [a for a in hijos_sub if a.get("mimeType") != MIME_CARPETA]
            sub_tiene_xml_txt = any(
                es_xml_o_txt_entrada(a.get("name", "")) for a in archivos_sub
            )
            sub_tiene_reporte = any(
                es_reporte_excel(a.get("name", "")) for a in archivos_sub
            )
            info_subcarpetas.append(
                {
                    "sub": sub,
                    "hijos": hijos_sub,
                    "archivos": archivos_sub,
                    "tiene_xml_txt": sub_tiene_xml_txt,
                    "tiene_reporte": sub_tiene_reporte,
                }
            )

        alguna_sub_con_reporte = any(s["tiene_reporte"] for s in info_subcarpetas)
        subs_sin_reporte = [
            s for s in info_subcarpetas if s["tiene_xml_txt"] and not s["tiene_reporte"]
        ]

        # Caso 1: Carpeta completa mal ubicada (sin reportes propios ni en subcarpetas)
        if (
            tiene_xml_txt_directo
            and not tiene_reporte_directo
            and not alguna_sub_con_reporte
        ):
            entrada_id = obtener_carpeta_entrada()
            existente_id = buscar_carpeta_hija(cliente, carpeta_nombre, entrada_id)

            # Si tenía subcarpetas sin reporte con archivos:
            for info_sub in info_subcarpetas:
                sub_obj = info_sub["sub"]
                sub_nombre = sub_obj.get("name", sub_obj["id"])
                if _es_nombre_fecha_pura(sub_nombre) and sub_nombre != carpeta_nombre:
                    destino_sub_fecha = buscar_o_crear_carpeta(cliente, sub_nombre, entrada_id)
                    for arch in info_sub["archivos"]:
                        if es_documento_entrada(arch.get("name", "")):
                            mover_archivo(cliente, arch["id"], destino_sub_fecha)
                            archivos_reubicados_ids.append(arch["id"])
                    _eliminar_archivo_seguro(cliente, sub_obj["id"])
                    if sub_nombre not in carpetas_reubicadas:
                        carpetas_reubicadas.append(sub_nombre)
                else:
                    for arch in info_sub["archivos"]:
                        if es_documento_entrada(arch.get("name", "")):
                            mover_archivo(
                                cliente,
                                arch["id"],
                                existente_id or carpeta_id,
                            )
                            archivos_reubicados_ids.append(arch["id"])
                    _eliminar_archivo_seguro(cliente, sub_obj["id"])

            if existente_id:
                for arch in archivos_directos:
                    mover_archivo(cliente, arch["id"], existente_id)
                    archivos_reubicados_ids.append(arch["id"])
                _eliminar_archivo_seguro(cliente, carpeta_id)
            else:
                mover_archivo(cliente, carpeta_id, entrada_id)
                archivos_reubicados_ids.extend(a["id"] for a in archivos_directos)

            carpetas_reubicadas.append(carpeta_nombre)
            logger.info(
                "Carpeta '%s' reubicada de %s a %s.",
                carpeta_nombre,
                CARPETA_REPORTES_HISTORICOS,
                CARPETA_ENTRADAS_AL_INVENTARIO,
            )
            continue

        # Caso 2: Subcarpetas sin reporte (o archivos directos sin reporte junto a subcarpetas ya procesadas)
        if subs_sin_reporte or (tiene_xml_txt_directo and not tiene_reporte_directo):
            entrada_id = obtener_carpeta_entrada()
            destino_fecha_id: str | None = None

            def obtener_destino_fecha_padre() -> str:
                nonlocal destino_fecha_id
                if not destino_fecha_id:
                    destino_fecha_id = buscar_o_crear_carpeta(
                        cliente,
                        carpeta_nombre,
                        entrada_id,
                    )
                return destino_fecha_id

            if tiene_xml_txt_directo and not tiene_reporte_directo:
                dest_padre = obtener_destino_fecha_padre()
                for arch in archivos_directos:
                    if es_documento_entrada(arch.get("name", "")):
                        mover_archivo(cliente, arch["id"], dest_padre)
                        archivos_reubicados_ids.append(arch["id"])
                if carpeta_nombre not in carpetas_reubicadas:
                    carpetas_reubicadas.append(carpeta_nombre)

            for info_sub in subs_sin_reporte:
                sub = info_sub["sub"]
                sub_nombre = sub.get("name", sub["id"])
                if _es_nombre_fecha_pura(sub_nombre) and sub_nombre != carpeta_nombre:
                    # La subcarpeta tiene nombre de fecha propio (ej. 30-10-2026 dentro de 20-10-2026)
                    dest_sub_propia = buscar_o_crear_carpeta(
                        cliente,
                        sub_nombre,
                        entrada_id,
                    )
                    for arch in info_sub["archivos"]:
                        if es_documento_entrada(arch.get("name", "")):
                            mover_archivo(cliente, arch["id"], dest_sub_propia)
                            archivos_reubicados_ids.append(arch["id"])
                    _eliminar_archivo_seguro(cliente, sub["id"])
                    if sub_nombre not in carpetas_reubicadas:
                        carpetas_reubicadas.append(sub_nombre)
                    logger.info(
                        "Subcarpeta de fecha '%s/%s' sin reporte reubicada a %s/%s.",
                        carpeta_nombre,
                        sub_nombre,
                        CARPETA_ENTRADAS_AL_INVENTARIO,
                        sub_nombre,
                    )
                else:
                    dest_padre = obtener_destino_fecha_padre()
                    for arch in info_sub["archivos"]:
                        if es_documento_entrada(arch.get("name", "")):
                            mover_archivo(cliente, arch["id"], dest_padre)
                            archivos_reubicados_ids.append(arch["id"])
                    _eliminar_archivo_seguro(cliente, sub["id"])
                    etiqueta = (
                        carpeta_nombre
                        if not alguna_sub_con_reporte and not tiene_reporte_directo
                        else f"{carpeta_nombre}/{sub_nombre}"
                    )
                    if etiqueta not in carpetas_reubicadas:
                        carpetas_reubicadas.append(etiqueta)
                    logger.info(
                        "Subcarpeta '%s/%s' sin reporte reubicada a %s/%s.",
                        carpeta_nombre,
                        sub_nombre,
                        CARPETA_ENTRADAS_AL_INVENTARIO,
                        carpeta_nombre,
                    )

            if not tiene_reporte_directo and not alguna_sub_con_reporte:
                restantes = _listar_hijos(cliente, carpeta_id)
                if not restantes:
                    _eliminar_archivo_seguro(cliente, carpeta_id)

    return {
        "carpetas_reubicadas": carpetas_reubicadas,
        "archivos_reubicados_ids": archivos_reubicados_ids,
    }


def revisar_carpetas_sin_reportes_drive(
    cliente: Any | None = None,
    carpeta_raiz_id: str | None = None,
) -> dict[str, Any]:
    """Inspecciona y lista qué carpetas en Drive tienen XMLs/TXTs pendientes sin reporte generado."""
    cliente = cliente or crear_cliente_drive()
    root_id = carpeta_raiz_id or settings.google_drive_folder_id
    if not root_id:
        raise GoogleDriveConfigError("Falta GOOGLE_DRIVE_FOLDER_ID")

    carpetas_sin_reporte: list[dict[str, Any]] = []
    archivos_sueltos: list[dict[str, str]] = []

    # 1. Inspeccionar ENTRADAS AL INVENTARIO
    carpeta_entrada_id = buscar_carpeta_hija(
        cliente,
        CARPETA_ENTRADAS_AL_INVENTARIO,
        root_id,
    )
    if carpeta_entrada_id:
        items_entrada = _listar_hijos(cliente, carpeta_entrada_id)
        for item in items_entrada:
            nombre = item.get("name", "")
            if item.get("mimeType") != MIME_CARPETA:
                if es_xml_o_txt_entrada(nombre):
                    archivos_sueltos.append(
                        {"nombre": nombre, "ubicacion": CARPETA_ENTRADAS_AL_INVENTARIO}
                    )
                continue
            if es_carpeta_archivos_sueltos(nombre):
                continue

            hijos = _listar_hijos(cliente, item["id"])
            archivos = [h for h in hijos if h.get("mimeType") != MIME_CARPETA]
            subcarpetas = [h for h in hijos if h.get("mimeType") == MIME_CARPETA]

            tiene_reporte = any(es_reporte_excel(a.get("name", "")) for a in archivos)
            conteo = _contar_documentos_entrada(archivos)

            for sub in subcarpetas:
                hijos_sub = _listar_hijos(cliente, sub["id"])
                if any(es_reporte_excel(a.get("name", "")) for a in hijos_sub):
                    tiene_reporte = True
                conteo_sub = _contar_documentos_entrada(hijos_sub)
                conteo["xmls"] += conteo_sub["xmls"]
                conteo["txts"] += conteo_sub["txts"]
                conteo["pdfs"] += conteo_sub["pdfs"]

            if (conteo["xmls"] > 0 or conteo["txts"] > 0) and not tiene_reporte:
                carpetas_sin_reporte.append(
                    {
                        "nombre": nombre,
                        "ubicacion": CARPETA_ENTRADAS_AL_INVENTARIO,
                        "xmls": conteo["xmls"],
                        "txts": conteo["txts"],
                        "pdfs": conteo["pdfs"],
                        "mal_ubicada": False,
                    }
                )

    # 2. Inspeccionar DOCUMENTOS ENTRADA
    carpeta_historico_id = buscar_carpeta_hija(
        cliente,
        CARPETA_REPORTES_HISTORICOS,
        root_id,
    )
    if carpeta_historico_id:
        items_historico = _listar_hijos(cliente, carpeta_historico_id)
        for item in items_historico:
            nombre = item.get("name", "")
            if item.get("mimeType") != MIME_CARPETA and es_xml_o_txt_entrada(nombre):
                archivos_sueltos.append(
                    {"nombre": nombre, "ubicacion": CARPETA_REPORTES_HISTORICOS}
                )

        carpetas_historico = listar_carpetas_fecha_en_historico(
            cliente,
            carpeta_historico_id,
            fn_listar_hijos=_listar_hijos,
        )
        for item in carpetas_historico:
            nombre = item.get("name", "")
            if es_carpeta_archivos_sueltos(nombre):
                continue

            hijos = _listar_hijos(cliente, item["id"])
            archivos = [h for h in hijos if h.get("mimeType") != MIME_CARPETA]
            subcarpetas = [h for h in hijos if h.get("mimeType") == MIME_CARPETA]

            tiene_reporte_directo = any(
                es_reporte_excel(a.get("name", "")) for a in archivos
            )
            conteo_directo = _contar_documentos_entrada(archivos)

            if (
                conteo_directo["xmls"] > 0 or conteo_directo["txts"] > 0
            ) and not tiene_reporte_directo:
                carpetas_sin_reporte.append(
                    {
                        "nombre": nombre,
                        "ubicacion": CARPETA_REPORTES_HISTORICOS,
                        "xmls": conteo_directo["xmls"],
                        "txts": conteo_directo["txts"],
                        "pdfs": conteo_directo["pdfs"],
                        "mal_ubicada": True,
                    }
                )

            for sub in subcarpetas:
                sub_nombre = sub.get("name", "")
                hijos_sub = _listar_hijos(cliente, sub["id"])
                archivos_sub = [
                    a for a in hijos_sub if a.get("mimeType") != MIME_CARPETA
                ]
                sub_tiene_reporte = any(
                    es_reporte_excel(a.get("name", "")) for a in archivos_sub
                )
                conteo_sub = _contar_documentos_entrada(archivos_sub)
                if (
                    conteo_sub["xmls"] > 0 or conteo_sub["txts"] > 0
                ) and not sub_tiene_reporte:
                    carpetas_sin_reporte.append(
                        {
                            "nombre": f"{nombre}/{sub_nombre}",
                            "ubicacion": CARPETA_REPORTES_HISTORICOS,
                            "xmls": conteo_sub["xmls"],
                            "txts": conteo_sub["txts"],
                            "pdfs": conteo_sub["pdfs"],
                            "mal_ubicada": True,
                        }
                    )

    en_entradas = [
        c["nombre"] for c in carpetas_sin_reporte if not c["mal_ubicada"]
    ]
    en_documentos = [
        c["nombre"] for c in carpetas_sin_reporte if c["mal_ubicada"]
    ]

    return {
        "ok": True,
        "tipo": "revisar_carpetas_sin_reportes",
        "carpetas_sin_reporte": carpetas_sin_reporte,
        "en_entradas_al_inventario": en_entradas,
        "en_documentos_entrada": en_documentos,
        "archivos_sueltos": archivos_sueltos,
        "total_pendientes": len(carpetas_sin_reporte),
    }


def _tiene_reporte_carpeta(cliente: Any, hijos: list[dict]) -> bool:
    """Indica si una carpeta (o alguna de sus subcarpetas directas) contiene un reporte Excel."""
    archivos = [h for h in hijos if h.get("mimeType") != MIME_CARPETA]
    if any(es_reporte_excel(a.get("name", "")) for a in archivos):
        return True
    subcarpetas = [h for h in hijos if h.get("mimeType") == MIME_CARPETA]
    for sub in subcarpetas:
        hijos_sub = _listar_hijos(cliente, sub["id"])
        if any(
            es_reporte_excel(a.get("name", ""))
            for a in hijos_sub
            if a.get("mimeType") != MIME_CARPETA
        ):
            return True
    return False


def mover_carpetas_con_reportes_drive(
    cliente: Any | None = None,
    carpeta_raiz_id: str | None = None,
) -> dict[str, Any]:
    """Traslada a DOCUMENTOS ENTRADA (bajo AÑO/MES/DD-MM-YYYY) las carpetas de ENTRADAS AL INVENTARIO
    que ya tienen reporte Excel, y organiza en AÑO/MES cualquier carpeta de fecha plana ya existente en DOCUMENTOS ENTRADA.
    """
    cliente = cliente or crear_cliente_drive()
    root_id = carpeta_raiz_id or settings.google_drive_folder_id
    if not root_id:
        raise GoogleDriveConfigError("Falta GOOGLE_DRIVE_FOLDER_ID")

    carpeta_entrada_id = buscar_carpeta_hija(
        cliente,
        CARPETA_ENTRADAS_AL_INVENTARIO,
        root_id,
    )
    carpeta_historico_id = buscar_carpeta_hija(
        cliente,
        CARPETA_REPORTES_HISTORICOS,
        root_id,
    )

    carpetas_movidas: list[str] = []

    if carpeta_entrada_id:
        items_entrada = _listar_hijos(cliente, carpeta_entrada_id)
        carpetas_entrada = [
            item
            for item in items_entrada
            if item.get("mimeType") == MIME_CARPETA
            and not es_carpeta_archivos_sueltos(item.get("name", ""))
        ]

        for carpeta in carpetas_entrada:
            carpeta_id = carpeta["id"]
            carpeta_nombre = carpeta.get("name", carpeta_id)
            hijos = _listar_hijos(cliente, carpeta_id)
            if not _tiene_reporte_carpeta(cliente, hijos):
                continue

            if not carpeta_historico_id:
                carpeta_historico_id = buscar_o_crear_carpeta(
                    cliente,
                    CARPETA_REPORTES_HISTORICOS,
                    root_id,
                )

            carpeta_destino_padre_id = obtener_o_crear_carpeta_mes_historico(
                cliente,
                carpeta_historico_id,
                carpeta_nombre,
                fn_buscar_o_crear=buscar_o_crear_carpeta,
            )
            destino_existente_id = buscar_carpeta_hija(
                cliente,
                carpeta_nombre,
                carpeta_destino_padre_id,
            )
            if destino_existente_id and destino_existente_id != carpeta_id:
                _mover_contenido_carpeta(cliente, carpeta_id, destino_existente_id, hijos)
            else:
                mover_archivo(cliente, carpeta_id, carpeta_destino_padre_id)

            carpetas_movidas.append(carpeta_nombre)
            logger.info(
                "Carpeta procesada '%s' trasladada de %s a %s.",
                carpeta_nombre,
                CARPETA_ENTRADAS_AL_INVENTARIO,
                CARPETA_REPORTES_HISTORICOS,
            )

    # Organizar también carpetas de fecha planas ya ubicadas en DOCUMENTOS ENTRADA hacia AÑO/MES/DD-MM-YYYY
    if carpeta_historico_id:
        carpetas_en_historico = listar_carpetas_fecha_en_historico(
            cliente,
            carpeta_historico_id,
            fn_listar_hijos=_listar_hijos,
        )
        for carp_hist in carpetas_en_historico:
            if carp_hist.get("en_jerarquia_anio_mes", False):
                continue
            carp_id = carp_hist["id"]
            carp_nombre = carp_hist.get("name", carp_id)
            if not extraer_anio_mes_de_fecha_carpeta(carp_nombre):
                continue
            hijos_hist = _listar_hijos(cliente, carp_id)
            if not _tiene_reporte_carpeta(cliente, hijos_hist):
                continue

            carpeta_mes_id = obtener_o_crear_carpeta_mes_historico(
                cliente,
                carpeta_historico_id,
                carp_nombre,
                fn_buscar_o_crear=buscar_o_crear_carpeta,
            )
            if carpeta_mes_id == carp_hist.get("padre_id"):
                continue

            destino_existente_id = buscar_carpeta_hija(
                cliente,
                carp_nombre,
                carpeta_mes_id,
            )
            if destino_existente_id and destino_existente_id != carp_id:
                _mover_contenido_carpeta(cliente, carp_id, destino_existente_id, hijos_hist)
            else:
                mover_archivo(cliente, carp_id, carpeta_mes_id)

            if carp_nombre not in carpetas_movidas:
                carpetas_movidas.append(carp_nombre)
            logger.info(
                "Carpeta histórica '%s' organizada en jerarquía AÑO/MES dentro de %s.",
                carp_nombre,
                CARPETA_REPORTES_HISTORICOS,
            )

    return {
        "ok": True,
        "tipo": "mover_carpetas_con_reportes",
        "carpetas_movidas": carpetas_movidas,
        "total_movidas": len(carpetas_movidas),
    }


def _limpiar_carpetas_vacias_en(cliente: Any, carpeta_padre_id: str) -> list[str]:
    """Elimina subcarpetas vacías (hasta 4 niveles, incluyendo AÑO/MES/FECHA/PROVEEDOR) dentro de carpeta_padre_id."""
    eliminadas: list[str] = []

    def _limpiar_nodo(nodo_id: str, ruta_relativa: str, nivel: int) -> bool:
        elementos = _listar_hijos(cliente, nodo_id)
        subcarpetas = [e for e in elementos if e.get("mimeType") == MIME_CARPETA]
        sub_eliminadas = 0
        if nivel < 4:
            for sub in subcarpetas:
                sub_id = sub["id"]
                sub_nombre = sub.get("name", sub_id)
                sub_ruta = f"{ruta_relativa}/{sub_nombre}"
                if _limpiar_nodo(sub_id, sub_ruta, nivel + 1):
                    sub_eliminadas += 1
        if len(elementos) - sub_eliminadas == 0:
            if _eliminar_archivo_seguro(cliente, nodo_id):
                eliminadas.append(ruta_relativa)
                return True
        return False

    hijos = _listar_hijos(cliente, carpeta_padre_id)
    for carpeta in hijos:
        if carpeta.get("mimeType") == MIME_CARPETA:
            carpeta_id = carpeta["id"]
            carpeta_nombre = carpeta.get("name", carpeta_id)
            _limpiar_nodo(carpeta_id, carpeta_nombre, 1)

    return eliminadas


def ordenar_todo_drive(
    cliente: Any | None = None,
    carpeta_raiz_id: str | None = None,
    fecha_actual: str | None = None,
) -> dict[str, Any]:
    """Reubica carpetas mal puestas, mueve carpetas con reporte, agrupa archivos sueltos para revisión manual y limpia vacías."""
    cliente = cliente or crear_cliente_drive()
    root_id = carpeta_raiz_id or settings.google_drive_folder_id
    if not root_id:
        raise GoogleDriveConfigError("Falta GOOGLE_DRIVE_FOLDER_ID")

    # 1. Reubicar carpetas sin reporte en DOCUMENTOS ENTRADA -> ENTRADAS AL INVENTARIO
    reubicacion = reubicar_carpetas_mal_ubicadas(cliente, root_id)
    carpetas_reubicadas = reubicacion["carpetas_reubicadas"]
    archivos_reubicados_ids = set(reubicacion["archivos_reubicados_ids"])

    # 2. Mover carpetas que ya tienen reporte en ENTRADAS AL INVENTARIO -> DOCUMENTOS ENTRADA
    movidas_con_reporte = mover_carpetas_con_reportes_drive(cliente, root_id)
    carpetas_con_reporte_movidas = movidas_con_reporte["carpetas_movidas"]

    # 3. Agrupar archivos sueltos en una carpeta con la fecha actual para intervención manual
    archivos_sueltos_acomodados: list[str] = []
    carpeta_entrada_id = buscar_carpeta_hija(
        cliente,
        CARPETA_ENTRADAS_AL_INVENTARIO,
        root_id,
    )
    carpeta_historico_id = buscar_carpeta_hija(
        cliente,
        CARPETA_REPORTES_HISTORICOS,
        root_id,
    )

    contenedores_a_revisar = [("RAIZ", root_id)]
    if carpeta_entrada_id:
        contenedores_a_revisar.append(
            (CARPETA_ENTRADAS_AL_INVENTARIO, carpeta_entrada_id)
        )
    if carpeta_historico_id:
        contenedores_a_revisar.append(
            (CARPETA_REPORTES_HISTORICOS, carpeta_historico_id)
        )

    fecha_carpeta_sueltos = fecha_actual or datetime.now().strftime("%d-%m-%Y")
    nombre_carpeta_sueltos = f"{PREFIJO_CARPETA_ARCHIVOS_SUELTOS}{fecha_carpeta_sueltos}"
    carpeta_sueltos_id: str | None = None

    for _, contenedor_id in contenedores_a_revisar:
        elementos = _listar_hijos(cliente, contenedor_id)
        for item in elementos:
            if item.get("mimeType") == MIME_CARPETA:
                continue
            nombre = item.get("name", "")
            item_id = item["id"]

            if es_documento_entrada(nombre) or es_archivo_generado(nombre):
                if not carpeta_sueltos_id:
                    carpeta_sueltos_id = buscar_o_crear_carpeta(
                        cliente,
                        nombre_carpeta_sueltos,
                        root_id,
                    )
                mover_archivo(cliente, item_id, carpeta_sueltos_id)
                archivos_sueltos_acomodados.append(nombre)
                archivos_reubicados_ids.add(item_id)

    # 4. Limpiar carpetas vacías en ENTRADAS AL INVENTARIO y DOCUMENTOS ENTRADA
    carpetas_vacias_eliminadas: list[str] = []
    if carpeta_entrada_id:
        carpetas_vacias_eliminadas.extend(
            _limpiar_carpetas_vacias_en(cliente, carpeta_entrada_id)
        )
    if carpeta_historico_id:
        carpetas_vacias_eliminadas.extend(
            _limpiar_carpetas_vacias_en(cliente, carpeta_historico_id)
        )

    # Si hubo archivos reubicados/acomodados, limpiarlos del estado local para que se procesen cuando sean organizados
    if archivos_reubicados_ids:
        ruta_estado = Path(CARPETA_DATOS) / NOMBRE_ESTADO
        if ruta_estado.is_file():
            estado = cargar_estado(ruta_estado)
            procesados = estado.get("archivos", {})
            modificado = False
            for arch_id in archivos_reubicados_ids:
                if arch_id in procesados:
                    del procesados[arch_id]
                    modificado = True
            if modificado:
                guardar_estado(ruta_estado, estado)

    salida: dict[str, Any] = {
        "ok": True,
        "tipo": "ordenar_todo",
        "carpetas_reubicadas": carpetas_reubicadas,
        "carpetas_con_reporte_movidas": carpetas_con_reporte_movidas,
        "archivos_sueltos_acomodados": archivos_sueltos_acomodados,
        "carpetas_vacias_eliminadas": carpetas_vacias_eliminadas,
    }
    if archivos_sueltos_acomodados:
        salida["carpeta_archivos_sueltos"] = nombre_carpeta_sueltos
        salida["advertencia_archivos_sueltos"] = construir_advertencia_archivos_sueltos(
            archivos_sueltos_acomodados,
            nombre_carpeta_sueltos,
        )

    return salida


__all__ = [
    "PREFIJO_CARPETA_ARCHIVOS_SUELTOS",
    "construir_advertencia_archivos_sueltos",
    "construir_advertencia_ubicacion",
    "construir_aviso_reubicacion_previa",
    "es_archivo_generado",
    "es_carpeta_archivos_sueltos",
    "es_documento_entrada",
    "es_reporte_excel",
    "es_xml_o_txt_entrada",
    "mover_carpetas_con_reportes_drive",
    "ordenar_todo_drive",
    "reubicar_carpetas_mal_ubicadas",
    "revisar_carpetas_sin_reportes_drive",
]
