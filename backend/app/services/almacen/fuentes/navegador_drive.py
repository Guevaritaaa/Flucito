"""Servicio de navegación, exploración por rutas, auditoría de facturas y gestión puntual en Google Drive."""

from __future__ import annotations

import re
import tempfile
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.services.almacen import extractor
from app.services.almacen.fuentes.google_drive import MIME_CARPETA, DriveArchivo
from app.services.almacen.fuentes.google_drive_client import (
    CARPETA_ENTRADAS_AL_INVENTARIO,
    CARPETA_REPORTES_HISTORICOS,
    PREFIJO_REPORTE,
    GoogleDriveConfigError,
    _listar_hijos,
    buscar_carpeta_hija,
    buscar_o_crear_carpeta,
    crear_cliente_drive,
    descargar_archivo,
    eliminar_archivo,
    mover_archivo,
    normalizar_fecha_reporte,
)
from app.services.almacen.fuentes.organizador import (
    es_archivo_generado,
    es_carpeta_archivos_sueltos,
    es_reporte_excel,
)


ALIAS_ENTRADAS = {
    "entradas_al_inventario",
    "entradas al inventario",
    "entradas",
}
ALIAS_HISTORICOS = {
    "documentos_entrada",
    "documentos entrada",
    "historicos",
    "históricos",
}
ALIAS_RAIZ = {"raiz", "raíz", "root", "/"}


def _normalizar_segmento_contenedor(segmento: str) -> str:
    """Convierte alias comunes de contenedores principales a su nombre oficial en Google Drive."""
    limpio = segmento.strip().casefold()
    if limpio in ALIAS_ENTRADAS:
        return CARPETA_ENTRADAS_AL_INVENTARIO
    if limpio in ALIAS_HISTORICOS:
        return CARPETA_REPORTES_HISTORICOS
    return segmento.strip()


def _intentar_normalizar_fecha(texto: str) -> str:
    """Si el texto representa una fecha válida (ej. 2026-03-18), devuelve DD-MM-AAAA; si no, devuelve el texto original."""
    limpio = texto.strip()
    try:
        return normalizar_fecha_reporte(limpio)
    except ValueError:
        return limpio


def _extraer_fecha_carpeta(nombre: str) -> tuple[int, int, int] | None:
    """Extrae (año, mes, día) si el nombre de la carpeta contiene una fecha DD-MM-AAAA o AAAA-MM-DD."""
    texto = (nombre or "").strip()
    m_dmy = re.search(r"\b(\d{2})-(\d{2})-(\d{4})\b", texto)
    if m_dmy:
        dia, mes, anio = int(m_dmy.group(1)), int(m_dmy.group(2)), int(m_dmy.group(3))
        if 1 <= mes <= 12 and 1 <= dia <= 31:
            return (anio, mes, dia)
    m_ymd = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", texto)
    if m_ymd:
        anio, mes, dia = int(m_ymd.group(1)), int(m_ymd.group(2)), int(m_ymd.group(3))
        if 1 <= mes <= 12 and 1 <= dia <= 31:
            return (anio, mes, dia)
    return None


def _clave_orden_carpeta(nombre: str) -> tuple[int, int, int, int, str]:
    """Ordena carpetas sin fecha primero alfabéticamente y carpetas con fecha en orden cronológico (más antigua a más reciente)."""
    fecha = _extraer_fecha_carpeta(nombre)
    if fecha is not None:
        return (1, fecha[0], fecha[1], fecha[2], (nombre or "").casefold())
    return (0, 0, 0, 0, (nombre or "").casefold())


def _obtener_rango_fechas_carpetas(nombres_carpetas: list[str]) -> tuple[str | None, str | None]:
    """Devuelve (carpeta_mas_antigua, carpeta_mas_reciente) considerando solo carpetas con fecha válida."""
    con_fecha: list[tuple[tuple[int, int, int], str]] = []
    for nombre in nombres_carpetas:
        fecha = _extraer_fecha_carpeta(nombre)
        if fecha is not None:
            con_fecha.append((fecha, nombre))
    if not con_fecha:
        return None, None
    con_fecha.sort(key=lambda item: item[0])
    return con_fecha[0][1], con_fecha[-1][1]


def _coincide_nombre_elemento(nombre_real: str, nombre_buscado: str) -> bool:
    """Compara nombres de archivos o carpetas ignorando mayúsculas y tolerando formatos de fecha equivalentes."""
    real_limpio = nombre_real.strip()
    buscado_limpio = nombre_buscado.strip()
    if real_limpio.casefold() == buscado_limpio.casefold():
        return True
    fecha_buscada = _intentar_normalizar_fecha(buscado_limpio)
    if real_limpio.casefold() == fecha_buscada.casefold():
        return True
    return False


def _extraer_clave_folio_nombre(nombre_archivo: str) -> tuple[str, int] | None:
    """Extrae clave (año, folio numérico) si el nombre contiene una secuencia de 6 o más dígitos."""
    coincidencia = re.search(r"(\d{6,})", Path(nombre_archivo).stem)
    if not coincidencia:
        return None
    digitos = coincidencia.group(1)
    return digitos[:4], int(digitos[4:])


def _extraer_folio_normalizado_nombre(nombre_archivo: str) -> str | None:
    """Extrae el folio normalizado sin ceros a la izquierda a partir del nombre del archivo."""
    stem = Path(nombre_archivo).stem
    coincidencia = re.search(r"(\d{6,})", stem)
    if coincidencia:
        digitos = coincidencia.group(1)
        anio = int(digitos[:4])
        if 2020 <= anio <= 2035 and len(digitos) > 4:
            return str(int(digitos[4:]))
        return str(int(digitos))

    grupos_digitos = re.findall(r"\d+", stem)
    if grupos_digitos:
        # Usar el último grupo numérico suele representar el folio cuando hay prefijos de fecha o serie
        ultimo_grupo = "".join(grupos_digitos)
        return str(int(ultimo_grupo))
    return None


def _archivos_comparten_folio(nombre_xml: str, nombre_apoyo: str) -> bool:
    """Determina si un archivo XML y un documento de apoyo (PDF/TXT) corresponden a la misma factura por nombre."""
    stem_xml = Path(nombre_xml).stem.casefold()
    stem_apoyo = Path(nombre_apoyo).stem.casefold()
    if stem_xml == stem_apoyo:
        return True

    clave_xml = _extraer_clave_folio_nombre(nombre_xml)
    clave_apoyo = _extraer_clave_folio_nombre(nombre_apoyo)
    if clave_xml is not None and clave_xml == clave_apoyo:
        return True

    folio_xml = _extraer_folio_normalizado_nombre(nombre_xml)
    folio_apoyo = _extraer_folio_normalizado_nombre(nombre_apoyo)
    if folio_xml is not None and folio_xml == folio_apoyo:
        return True

    return False


def resolver_ruta_drive(
    cliente: Any,
    ruta_objetivo: str,
    carpeta_raiz_id: str | None = None,
    excluir_padre_id: str | None = None,
) -> dict[str, Any]:
    """
    Resuelve una ruta legible o nombre de elemento en Google Drive a sus metadatos e ID.

    Soporta rutas completas (ej. 'ENTRADAS AL INVENTARIO/18-03-2026/factura.xml') o
    nombres directos de carpetas/archivos (ej. '18-03-2026'), buscando primero en la raíz
    y luego dentro de los contenedores principales.
    """
    raiz_id = carpeta_raiz_id or settings.google_drive_folder_id
    if not raiz_id:
        raise GoogleDriveConfigError("Falta GOOGLE_DRIVE_FOLDER_ID")

    ruta_limpia = (ruta_objetivo or "").strip().strip("/")
    if not ruta_limpia or ruta_limpia.casefold() in ALIAS_RAIZ:
        return {
            "id": raiz_id,
            "nombre": "RAIZ",
            "mimeType": MIME_CARPETA,
            "es_carpeta": True,
            "padre_id": None,
            "ruta_completa": "RAIZ",
        }

    segmentos = [seg.strip() for seg in ruta_limpia.split("/") if seg.strip()]
    if segmentos and segmentos[0].casefold() in ALIAS_RAIZ:
        segmentos = segmentos[1:]

    if not segmentos:
        return {
            "id": raiz_id,
            "nombre": "RAIZ",
            "mimeType": MIME_CARPETA,
            "es_carpeta": True,
            "padre_id": None,
            "ruta_completa": "RAIZ",
        }

    segmentos[0] = _normalizar_segmento_contenedor(segmentos[0])
    hijos_raiz = _listar_hijos(cliente, raiz_id)

    # Caso 1: Navegación explícita desde un elemento hijo directo de la raíz
    primer_segmento = segmentos[0]
    coincidencias_raiz = [
        item
        for item in hijos_raiz
        if _coincide_nombre_elemento(item.get("name", ""), primer_segmento)
    ]

    if coincidencias_raiz:
        elemento_actual = coincidencias_raiz[0]
        padre_actual_id = raiz_id
        partes_ruta = [elemento_actual.get("name", primer_segmento)]

        for indice in range(1, len(segmentos)):
            segmento_buscado = segmentos[indice]
            if elemento_actual.get("mimeType") != MIME_CARPETA:
                raise ValueError(
                    f"El elemento '{elemento_actual.get('name')}' no es una carpeta, "
                    f"no se puede navegar hacia '{segmento_buscado}'."
                )
            hijos_actuales = _listar_hijos(cliente, elemento_actual["id"])
            siguiente = next(
                (
                    hijo
                    for hijo in hijos_actuales
                    if _coincide_nombre_elemento(hijo.get("name", ""), segmento_buscado)
                ),
                None,
            )
            if not siguiente:
                raise ValueError(
                    f"No se encontró '{segmento_buscado}' dentro de '{'/'.join(partes_ruta)}'."
                )
            padre_actual_id = elemento_actual["id"]
            elemento_actual = siguiente
            partes_ruta.append(elemento_actual.get("name", segmento_buscado))

        return {
            "id": elemento_actual["id"],
            "nombre": elemento_actual.get("name", ""),
            "mimeType": elemento_actual.get("mimeType", ""),
            "es_carpeta": elemento_actual.get("mimeType") == MIME_CARPETA,
            "padre_id": padre_actual_id,
            "ruta_completa": "/".join(partes_ruta),
        }

    # Caso 2: Ruta relativa o nombre corto (ej. '18-03-2026' o '18-03-2026/factura.xml')
    contenedores_principales = [
        item
        for item in hijos_raiz
        if item.get("mimeType") == MIME_CARPETA
        and item.get("name") in {CARPETA_ENTRADAS_AL_INVENTARIO, CARPETA_REPORTES_HISTORICOS}
    ]
    # Ordenar priorizando ENTRADAS AL INVENTARIO primero
    contenedores_principales.sort(
        key=lambda item: 0 if item.get("name") == CARPETA_ENTRADAS_AL_INVENTARIO else 1
    )

    candidatos_encontrados: list[dict[str, Any]] = []

    for contenedor in contenedores_principales:
        nombre_contenedor = contenedor.get("name", "")
        hijos_contenedor = _listar_hijos(cliente, contenedor["id"])

        for hijo in hijos_contenedor:
            if _coincide_nombre_elemento(hijo.get("name", ""), primer_segmento):
                elemento_actual = hijo
                padre_actual_id = contenedor["id"]
                partes_ruta = [nombre_contenedor, elemento_actual.get("name", "")]
                ruta_valida = True

                for indice in range(1, len(segmentos)):
                    segmento_buscado = segmentos[indice]
                    if elemento_actual.get("mimeType") != MIME_CARPETA:
                        ruta_valida = False
                        break
                    nietos = _listar_hijos(cliente, elemento_actual["id"])
                    siguiente = next(
                        (
                            nieto
                            for nieto in nietos
                            if _coincide_nombre_elemento(nieto.get("name", ""), segmento_buscado)
                        ),
                        None,
                    )
                    if not siguiente:
                        ruta_valida = False
                        break
                    padre_actual_id = elemento_actual["id"]
                    elemento_actual = siguiente
                    partes_ruta.append(elemento_actual.get("name", ""))

                if ruta_valida:
                    candidatos_encontrados.append(
                        {
                            "id": elemento_actual["id"],
                            "nombre": elemento_actual.get("name", ""),
                            "mimeType": elemento_actual.get("mimeType", ""),
                            "es_carpeta": elemento_actual.get("mimeType") == MIME_CARPETA,
                            "padre_id": padre_actual_id,
                            "ruta_completa": "/".join(partes_ruta),
                        }
                    )

    if excluir_padre_id and len(candidatos_encontrados) > 1:
        filtrados = [
            cand for cand in candidatos_encontrados if cand["padre_id"] != excluir_padre_id
        ]
        if filtrados:
            candidatos_encontrados = filtrados

    if candidatos_encontrados:
        return candidatos_encontrados[0]

    # Caso 3: Búsqueda de un archivo o subcarpeta de proveedor un nivel más abajo (cuando solo pasan el nombre)
    if len(segmentos) == 1:
        nombre_buscado = segmentos[0]
        for contenedor in contenedores_principales:
            nombre_contenedor = contenedor.get("name", "")
            for carpeta_fecha in _listar_hijos(cliente, contenedor["id"]):
                if carpeta_fecha.get("mimeType") != MIME_CARPETA:
                    continue
                for subitem in _listar_hijos(cliente, carpeta_fecha["id"]):
                    if _coincide_nombre_elemento(subitem.get("name", ""), nombre_buscado):
                        return {
                            "id": subitem["id"],
                            "nombre": subitem.get("name", ""),
                            "mimeType": subitem.get("mimeType", ""),
                            "es_carpeta": subitem.get("mimeType") == MIME_CARPETA,
                            "padre_id": carpeta_fecha["id"],
                            "ruta_completa": (
                                f"{nombre_contenedor}/{carpeta_fecha.get('name', '')}/"
                                f"{subitem.get('name', '')}"
                            ),
                        }

    raise ValueError(
        f"No se encontró la carpeta o archivo '{ruta_objetivo}' en Google Drive."
    )


def _resumir_elementos_carpeta(
    cliente: Any,
    carpeta_id: str,
    nombre_carpeta: str,
    ruta_carpeta: str,
    incluir_archivos: bool = True,
    profundidad_maxima: int = 2,
) -> dict[str, Any]:
    """Construye el resumen estructurado de una carpeta de Drive y sus archivos/subcarpetas."""
    hijos = _listar_hijos(cliente, carpeta_id)
    subcarpetas_raw = [h for h in hijos if h.get("mimeType") == MIME_CARPETA]
    archivos_raw = [h for h in hijos if h.get("mimeType") != MIME_CARPETA]

    conteo = {
        "xml": 0,
        "pdf": 0,
        "txt": 0,
        "xlsx_reportes": 0,
        "otros": 0,
    }
    nombres_archivos: list[str] = []

    for archivo in archivos_raw:
        nombre = archivo.get("name", "")
        nombres_archivos.append(nombre)
        extension = Path(nombre).suffix.lower()
        if es_reporte_excel(nombre):
            conteo["xlsx_reportes"] += 1
        elif extension == ".xml" and not es_archivo_generado(nombre):
            conteo["xml"] += 1
        elif extension == ".pdf" and not es_archivo_generado(nombre):
            conteo["pdf"] += 1
        elif extension == ".txt" and not es_archivo_generado(nombre):
            conteo["txt"] += 1
        else:
            conteo["otros"] += 1

    subcarpetas_ordenadas = sorted(
        subcarpetas_raw,
        key=lambda x: _clave_orden_carpeta(x.get("name", "")),
    )
    subcarpetas_info: list[dict[str, Any]] = []
    if profundidad_maxima > 0:
        for sub in subcarpetas_ordenadas:
            nombre_sub = sub.get("name", "")
            resumen_sub = _resumir_elementos_carpeta(
                cliente=cliente,
                carpeta_id=sub["id"],
                nombre_carpeta=nombre_sub,
                ruta_carpeta=f"{ruta_carpeta}/{nombre_sub}",
                incluir_archivos=incluir_archivos,
                profundidad_maxima=profundidad_maxima - 1,
            )
            subcarpetas_info.append(resumen_sub)

    resultado: dict[str, Any] = {
        "id": carpeta_id,
        "nombre": nombre_carpeta,
        "ruta": ruta_carpeta,
        "total_archivos_directos": len(archivos_raw),
        "total_subcarpetas": len(subcarpetas_raw),
        "conteo_archivos": conteo,
        "subcarpetas": subcarpetas_info,
    }
    if profundidad_maxima == 0 and subcarpetas_ordenadas:
        resultado["nombres_subcarpetas"] = [
            s.get("name", "") for s in subcarpetas_ordenadas
        ]
    if incluir_archivos:
        resultado["archivos"] = sorted(nombres_archivos, key=str.casefold)
    return resultado


def explorar_estructura_drive(
    ubicacion: str = "todas",
    carpeta_o_fecha: str | None = None,
    incluir_archivos: bool = True,
    cliente: Any | None = None,
    carpeta_raiz_id: str | None = None,
) -> dict[str, Any]:
    """
    Explora y lista las carpetas y archivos existentes en Google Drive sin modificarlos.

    Permite inspeccionar todo el Drive, un contenedor específico ('entradas_al_inventario',
    'documentos_entrada', 'raiz') o una carpeta/fecha particular.
    """
    cliente = cliente or crear_cliente_drive()
    raiz_id = carpeta_raiz_id or settings.google_drive_folder_id
    if not raiz_id:
        raise GoogleDriveConfigError("Falta GOOGLE_DRIVE_FOLDER_ID")

    # Si se especificó una carpeta o fecha puntual, inspeccionarla en las ubicaciones pertinentes
    if carpeta_o_fecha and carpeta_o_fecha.strip():
        objetivo_texto = carpeta_o_fecha.strip()
        # Si ya incluye barra o alias explícito, resolver directamente
        if "/" in objetivo_texto:
            meta_objetivo = resolver_ruta_drive(cliente, objetivo_texto, carpeta_raiz_id=raiz_id)
            if not meta_objetivo["es_carpeta"]:
                return {
                    "ok": True,
                    "tipo": "explorar_estructura",
                    "elemento_encontrado": meta_objetivo,
                    "mensaje": f"Se encontró el archivo '{meta_objetivo['ruta_completa']}'.",
                }
            detalle = _resumir_elementos_carpeta(
                cliente=cliente,
                carpeta_id=meta_objetivo["id"],
                nombre_carpeta=meta_objetivo["nombre"],
                ruta_carpeta=meta_objetivo["ruta_completa"],
                incluir_archivos=incluir_archivos,
            )
            return {
                "ok": True,
                "tipo": "explorar_estructura",
                "filtro_carpeta": objetivo_texto,
                "carpetas_encontradas": [detalle],
                "total_carpetas_encontradas": 1,
                "mensaje": f"Se inspeccionó la carpeta '{meta_objetivo['ruta_completa']}'.",
            }

        # Buscar la carpeta por nombre/fecha en las ubicaciones solicitadas
        hijos_raiz = _listar_hijos(cliente, raiz_id)
        mapa_contenedores = {
            item.get("name"): item["id"]
            for item in hijos_raiz
            if item.get("mimeType") == MIME_CARPETA
        }

        contenedores_a_buscar: list[tuple[str, str]] = []
        if ubicacion in {"todas", "entradas_al_inventario"} and CARPETA_ENTRADAS_AL_INVENTARIO in mapa_contenedores:
            contenedores_a_buscar.append(
                (CARPETA_ENTRADAS_AL_INVENTARIO, mapa_contenedores[CARPETA_ENTRADAS_AL_INVENTARIO])
            )
        if ubicacion in {"todas", "documentos_entrada"} and CARPETA_REPORTES_HISTORICOS in mapa_contenedores:
            contenedores_a_buscar.append(
                (CARPETA_REPORTES_HISTORICOS, mapa_contenedores[CARPETA_REPORTES_HISTORICOS])
            )

        carpetas_coincidentes: list[dict[str, Any]] = []
        for nombre_cont, id_cont in contenedores_a_buscar:
            for hijo in _listar_hijos(cliente, id_cont):
                if hijo.get("mimeType") == MIME_CARPETA and _coincide_nombre_elemento(
                    hijo.get("name", ""), objetivo_texto
                ):
                    carpetas_coincidentes.append(
                        _resumir_elementos_carpeta(
                            cliente=cliente,
                            carpeta_id=hijo["id"],
                            nombre_carpeta=hijo.get("name", ""),
                            ruta_carpeta=f"{nombre_cont}/{hijo.get('name', '')}",
                            incluir_archivos=incluir_archivos,
                        )
                    )

        if not carpetas_coincidentes:
            # Intentar resolución general por si es una subcarpeta de proveedor o carpeta en raíz
            meta_objetivo = resolver_ruta_drive(cliente, objetivo_texto, carpeta_raiz_id=raiz_id)
            if meta_objetivo["es_carpeta"]:
                carpetas_coincidentes.append(
                    _resumir_elementos_carpeta(
                        cliente=cliente,
                        carpeta_id=meta_objetivo["id"],
                        nombre_carpeta=meta_objetivo["nombre"],
                        ruta_carpeta=meta_objetivo["ruta_completa"],
                        incluir_archivos=incluir_archivos,
                    )
                )

        return {
            "ok": True,
            "tipo": "explorar_estructura",
            "filtro_carpeta": objetivo_texto,
            "carpetas_encontradas": carpetas_coincidentes,
            "total_carpetas_encontradas": len(carpetas_coincidentes),
            "mensaje": (
                f"Se encontraron {len(carpetas_coincidentes)} carpeta(s) que coinciden con '{objetivo_texto}'."
                if carpetas_coincidentes
                else f"No se encontró ninguna carpeta llamada '{objetivo_texto}'."
            ),
        }

    # Exploración general por contenedor(es)
    hijos_raiz = _listar_hijos(cliente, raiz_id)
    carpetas_raiz = {
        item.get("name", ""): item["id"]
        for item in hijos_raiz
        if item.get("mimeType") == MIME_CARPETA
    }
    archivos_sueltos_raiz = [
        item.get("name", "")
        for item in hijos_raiz
        if item.get("mimeType") != MIME_CARPETA
    ]
    otras_carpetas_raiz = [
        item.get("name", "")
        for item in hijos_raiz
        if item.get("mimeType") == MIME_CARPETA
        and item.get("name") not in {CARPETA_ENTRADAS_AL_INVENTARIO, CARPETA_REPORTES_HISTORICOS}
    ]

    resultado_contenedores: dict[str, Any] = {}

    if ubicacion in {"todas", "entradas_al_inventario"}:
        entradas_id = carpetas_raiz.get(CARPETA_ENTRADAS_AL_INVENTARIO)
        if entradas_id:
            resumen_entradas = _resumir_elementos_carpeta(
                cliente=cliente,
                carpeta_id=entradas_id,
                nombre_carpeta=CARPETA_ENTRADAS_AL_INVENTARIO,
                ruta_carpeta=CARPETA_ENTRADAS_AL_INVENTARIO,
                incluir_archivos=incluir_archivos,
                profundidad_maxima=1,
            )
            nombres_entradas = [c["nombre"] for c in resumen_entradas["subcarpetas"]]
            antigua_ent, reciente_ent = _obtener_rango_fechas_carpetas(nombres_entradas)
            resultado_contenedores["entradas_al_inventario"] = {
                "id": entradas_id,
                "nombre": CARPETA_ENTRADAS_AL_INVENTARIO,
                "total_carpetas": len(resumen_entradas["subcarpetas"]),
                "carpeta_mas_antigua": antigua_ent,
                "carpeta_mas_reciente": reciente_ent,
                "nombres_carpetas": nombres_entradas,
                "carpetas": resumen_entradas["subcarpetas"],
                "archivos_sueltos": resumen_entradas.get("archivos", []),
            }
        else:
            resultado_contenedores["entradas_al_inventario"] = {
                "id": None,
                "nombre": CARPETA_ENTRADAS_AL_INVENTARIO,
                "total_carpetas": 0,
                "carpeta_mas_antigua": None,
                "carpeta_mas_reciente": None,
                "nombres_carpetas": [],
                "carpetas": [],
                "archivos_sueltos": [],
            }

    if ubicacion in {"todas", "documentos_entrada"}:
        historicos_id = carpetas_raiz.get(CARPETA_REPORTES_HISTORICOS)
        if historicos_id:
            resumen_historicos = _resumir_elementos_carpeta(
                cliente=cliente,
                carpeta_id=historicos_id,
                nombre_carpeta=CARPETA_REPORTES_HISTORICOS,
                ruta_carpeta=CARPETA_REPORTES_HISTORICOS,
                incluir_archivos=incluir_archivos,
                profundidad_maxima=1,
            )
            nombres_hist = [c["nombre"] for c in resumen_historicos["subcarpetas"]]
            antigua_hist, reciente_hist = _obtener_rango_fechas_carpetas(nombres_hist)
            resultado_contenedores["documentos_entrada"] = {
                "id": historicos_id,
                "nombre": CARPETA_REPORTES_HISTORICOS,
                "total_carpetas": len(resumen_historicos["subcarpetas"]),
                "carpeta_mas_antigua": antigua_hist,
                "carpeta_mas_reciente": reciente_hist,
                "nombres_carpetas": nombres_hist,
                "carpetas": resumen_historicos["subcarpetas"],
                "archivos_sueltos": resumen_historicos.get("archivos", []),
            }
        else:
            resultado_contenedores["documentos_entrada"] = {
                "id": None,
                "nombre": CARPETA_REPORTES_HISTORICOS,
                "total_carpetas": 0,
                "carpeta_mas_antigua": None,
                "carpeta_mas_reciente": None,
                "nombres_carpetas": [],
                "carpetas": [],
                "archivos_sueltos": [],
            }

    if ubicacion in {"todas", "raiz"}:
        resultado_contenedores["raiz"] = {
            "id": raiz_id,
            "otras_carpetas_en_raiz": sorted(otras_carpetas_raiz, key=str.casefold),
            "archivos_sueltos_en_raiz": sorted(archivos_sueltos_raiz, key=str.casefold),
        }

    total_en_entradas = (
        resultado_contenedores.get("entradas_al_inventario", {}).get("total_carpetas", 0)
    )
    total_en_historicos = (
        resultado_contenedores.get("documentos_entrada", {}).get("total_carpetas", 0)
    )
    todas_las_fechas = (
        resultado_contenedores.get("entradas_al_inventario", {}).get("nombres_carpetas", [])
        + resultado_contenedores.get("documentos_entrada", {}).get("nombres_carpetas", [])
    )
    carpeta_mas_antigua_global, carpeta_mas_reciente_global = _obtener_rango_fechas_carpetas(
        todas_las_fechas
    )

    return {
        "ok": True,
        "tipo": "explorar_estructura",
        "ubicacion_consultada": ubicacion,
        "contenedores": resultado_contenedores,
        "resumen": {
            "total_carpetas_en_entradas_al_inventario": total_en_entradas,
            "total_carpetas_en_documentos_entrada": total_en_historicos,
            "carpeta_mas_antigua_global": carpeta_mas_antigua_global,
            "carpeta_mas_reciente_global": carpeta_mas_reciente_global,
            "otras_carpetas_en_raiz": len(otras_carpetas_raiz),
            "archivos_sueltos_en_raiz": len(archivos_sueltos_raiz),
        },
        "mensaje": (
            f"Estructura de Google Drive consultada: {total_en_entradas} carpeta(s) en "
            f"ENTRADAS AL INVENTARIO y {total_en_historicos} carpeta(s) en DOCUMENTOS ENTRADA."
            + (
                f" La carpeta más reciente por fecha es '{carpeta_mas_reciente_global}'."
                if carpeta_mas_reciente_global
                else ""
            )
        ),
    }


def _auditar_carpeta_individual(
    cliente: Any,
    carpeta: dict[str, Any],
    nombre_contenedor: str,
) -> dict[str, Any]:
    """
    Evalúa la completitud documental de una carpeta (facturas XML, soportes PDF/TXT y reportes Excel).

    Cruza los nombres y folios de los archivos sin descargar su contenido para determinar
    qué facturas tienen soporte completo, cuáles están incompletas y si existe reporte Excel.
    """
    nombre_carpeta = carpeta.get("name", "")
    ruta_carpeta = f"{nombre_contenedor}/{nombre_carpeta}"
    hijos = _listar_hijos(cliente, carpeta["id"])

    subcarpetas = [h for h in hijos if h.get("mimeType") == MIME_CARPETA]
    archivos_directos = [h for h in hijos if h.get("mimeType") != MIME_CARPETA]

    # En DOCUMENTOS ENTRADA, los XML/PDF/TXT archivados suelen estar dentro de subcarpetas de proveedor
    todos_los_archivos = list(archivos_directos)
    nombres_subcarpetas: list[str] = []
    for sub in subcarpetas:
        nombres_subcarpetas.append(sub.get("name", ""))
        hijos_sub = _listar_hijos(cliente, sub["id"])
        todos_los_archivos.extend(
            [h for h in hijos_sub if h.get("mimeType") != MIME_CARPETA]
        )

    archivos_xml: list[str] = []
    archivos_apoyo: list[str] = []
    reportes_excel: list[str] = []
    otros_archivos: list[str] = []

    for item in todos_los_archivos:
        nombre = item.get("name", "")
        ext = Path(nombre).suffix.lower()
        if es_reporte_excel(nombre):
            reportes_excel.append(nombre)
        elif es_archivo_generado(nombre):
            otros_archivos.append(nombre)
        elif ext == ".xml":
            archivos_xml.append(nombre)
        elif ext in {".pdf", ".txt"}:
            archivos_apoyo.append(nombre)
        else:
            otros_archivos.append(nombre)

    # Emparejar cada XML con sus archivos de apoyo (PDF/TXT) por folio o nombre
    xml_con_apoyo: list[str] = []
    xml_sin_apoyo: list[str] = []
    apoyos_emparejados: set[str] = set()

    for nombre_xml in archivos_xml:
        coincidentes = [
            apoyo
            for apoyo in archivos_apoyo
            if _archivos_comparten_folio(nombre_xml, apoyo)
        ]
        if coincidentes:
            xml_con_apoyo.append(nombre_xml)
            apoyos_emparejados.update(coincidentes)
        else:
            xml_sin_apoyo.append(nombre_xml)

    apoyos_huerfanos = [
        apoyo for apoyo in archivos_apoyo if apoyo not in apoyos_emparejados
    ]

    tiene_xml = len(archivos_xml) > 0
    tiene_reporte_excel = len(reportes_excel) > 0
    esta_vacia = len(todos_los_archivos) == 0 and len(subcarpetas) == 0

    # Detectar si está mal ubicada en DOCUMENTOS ENTRADA (documentos directos sin reporte Excel)
    xml_o_txt_directos = any(
        Path(a.get("name", "")).suffix.lower() in {".xml", ".txt"}
        and not es_archivo_generado(a.get("name", ""))
        for a in archivos_directos
    )
    reporte_directo = any(es_reporte_excel(a.get("name", "")) for a in archivos_directos)
    mal_ubicada = (
        nombre_contenedor == CARPETA_REPORTES_HISTORICOS
        and not es_carpeta_archivos_sueltos(nombre_carpeta)
        and xml_o_txt_directos
        and not reporte_directo
        and not tiene_reporte_excel
    )

    problemas_detectados: list[str] = []
    if esta_vacia:
        problemas_detectados.append("carpeta_vacia")
    elif not tiene_xml:
        problemas_detectados.append("sin_facturas_xml")

    if xml_sin_apoyo:
        problemas_detectados.append("xml_sin_apoyo_pdf_o_txt")
    if apoyos_huerfanos:
        problemas_detectados.append("apoyos_sin_xml_correspondiente")
    if tiene_xml and not tiene_reporte_excel:
        problemas_detectados.append("sin_reporte_excel")
    if mal_ubicada:
        problemas_detectados.append("mal_ubicada_en_documentos_entrada")

    facturas_completas = tiene_xml and len(xml_sin_apoyo) == 0

    return {
        "id": carpeta["id"],
        "nombre": nombre_carpeta,
        "ubicacion": nombre_contenedor,
        "ruta": ruta_carpeta,
        "esta_vacia": esta_vacia,
        "tiene_xml": tiene_xml,
        "tiene_reporte_excel": tiene_reporte_excel,
        "facturas_completas": facturas_completas,
        "mal_ubicada": mal_ubicada,
        "total_xml": len(archivos_xml),
        "total_apoyos": len(archivos_apoyo),
        "total_reportes_excel": len(reportes_excel),
        "archivos_xml": sorted(archivos_xml, key=str.casefold),
        "xml_con_apoyo": sorted(xml_con_apoyo, key=str.casefold),
        "xml_sin_apoyo": sorted(xml_sin_apoyo, key=str.casefold),
        "apoyos_huerfanos": sorted(apoyos_huerfanos, key=str.casefold),
        "reportes_excel": sorted(reportes_excel, key=str.casefold),
        "subcarpetas": sorted(nombres_subcarpetas, key=str.casefold),
        "problemas": problemas_detectados,
    }


def auditar_facturas_drive(
    ubicacion: str = "todas",
    carpeta_o_fecha: str | None = None,
    filtro_auditoria: str = "todos",
    cliente: Any | None = None,
    carpeta_raiz_id: str | None = None,
) -> dict[str, Any]:
    """
    Realiza una auditoría rápida híbrida sobre las carpetas de Google Drive.

    Detecta:
    - Carpetas vacías o que no cuentan con facturas (.xml).
    - Facturas (.xml) que no tienen documento de respaldo (.pdf o .txt) con el mismo folio.
    - Archivos de soporte (.pdf/.txt) huérfanos sin factura (.xml).
    - Carpetas pendientes de generar reporte Excel (ENTRADAS_ALMACEN_*.xlsx).
    - Carpetas mal ubicadas dentro de DOCUMENTOS ENTRADA.
    """
    cliente = cliente or crear_cliente_drive()
    raiz_id = carpeta_raiz_id or settings.google_drive_folder_id
    if not raiz_id:
        raise GoogleDriveConfigError("Falta GOOGLE_DRIVE_FOLDER_ID")

    hijos_raiz = _listar_hijos(cliente, raiz_id)
    mapa_contenedores = {
        item.get("name", ""): item["id"]
        for item in hijos_raiz
        if item.get("mimeType") == MIME_CARPETA
    }

    contenedores_objetivo: list[tuple[str, str]] = []
    if ubicacion in {"todas", "entradas_al_inventario"} and CARPETA_ENTRADAS_AL_INVENTARIO in mapa_contenedores:
        contenedores_objetivo.append(
            (CARPETA_ENTRADAS_AL_INVENTARIO, mapa_contenedores[CARPETA_ENTRADAS_AL_INVENTARIO])
        )
    if ubicacion in {"todas", "documentos_entrada"} and CARPETA_REPORTES_HISTORICOS in mapa_contenedores:
        contenedores_objetivo.append(
            (CARPETA_REPORTES_HISTORICOS, mapa_contenedores[CARPETA_REPORTES_HISTORICOS])
        )

    auditorias: list[dict[str, Any]] = []
    filtro_nombre = carpeta_o_fecha.strip() if carpeta_o_fecha and carpeta_o_fecha.strip() else None

    for nombre_contenedor, contenedor_id in contenedores_objetivo:
        hijos_contenedor = _listar_hijos(cliente, contenedor_id)
        carpetas_hijas = [
            h for h in hijos_contenedor if h.get("mimeType") == MIME_CARPETA
        ]
        for carpeta in sorted(
            carpetas_hijas,
            key=lambda x: _clave_orden_carpeta(x.get("name", "")),
        ):
            nombre_c = carpeta.get("name", "")
            if es_carpeta_archivos_sueltos(nombre_c) and not filtro_nombre:
                continue
            if filtro_nombre and not _coincide_nombre_elemento(nombre_c, filtro_nombre):
                continue
            auditorias.append(
                _auditar_carpeta_individual(
                    cliente=cliente,
                    carpeta=carpeta,
                    nombre_contenedor=nombre_contenedor,
                )
            )

    # Clasificaciones rápidas para respuesta directa del agente
    carpetas_vacias = [a["ruta"] for a in auditorias if a["esta_vacia"]]
    carpetas_sin_xml = [a["ruta"] for a in auditorias if not a["tiene_xml"]]
    carpetas_con_xml_sin_apoyo = [
        {
            "ruta": a["ruta"],
            "xml_sin_apoyo": a["xml_sin_apoyo"],
            "apoyos_huerfanos": a["apoyos_huerfanos"],
        }
        for a in auditorias
        if a["xml_sin_apoyo"] or a["apoyos_huerfanos"]
    ]
    carpetas_sin_reporte_excel = [
        a["ruta"] for a in auditorias if a["tiene_xml"] and not a["tiene_reporte_excel"]
    ]
    carpetas_mal_ubicadas = [a["ruta"] for a in auditorias if a["mal_ubicada"]]
    carpetas_completas = [
        a["ruta"]
        for a in auditorias
        if a["facturas_completas"] and not a["apoyos_huerfanos"]
    ]

    # Filtrar el detalle devuelto según filtro_auditoria
    if filtro_auditoria == "sin_xml":
        auditorias_filtradas = [a for a in auditorias if not a["tiene_xml"]]
    elif filtro_auditoria == "sin_apoyo":
        auditorias_filtradas = [
            a for a in auditorias if a["xml_sin_apoyo"] or a["apoyos_huerfanos"]
        ]
    elif filtro_auditoria == "sin_reporte_excel":
        auditorias_filtradas = [
            a for a in auditorias if a["tiene_xml"] and not a["tiene_reporte_excel"]
        ]
    elif filtro_auditoria == "incompletas":
        auditorias_filtradas = [
            a
            for a in auditorias
            if not a["tiene_xml"]
            or a["xml_sin_apoyo"]
            or a["apoyos_huerfanos"]
            or not a["tiene_reporte_excel"]
        ]
    elif filtro_auditoria == "completas":
        auditorias_filtradas = [
            a
            for a in auditorias
            if a["facturas_completas"] and not a["apoyos_huerfanos"]
        ]
    else:
        auditorias_filtradas = auditorias

    return {
        "ok": True,
        "tipo": "auditar_facturas",
        "ubicacion_consultada": ubicacion,
        "filtro_auditoria": filtro_auditoria,
        "total_carpetas_evaluadas": len(auditorias),
        "resumen_hallazgos": {
            "carpetas_sin_xml": carpetas_sin_xml,
            "carpetas_vacias": carpetas_vacias,
            "carpetas_con_xml_sin_apoyo": carpetas_con_xml_sin_apoyo,
            "carpetas_sin_reporte_excel": carpetas_sin_reporte_excel,
            "carpetas_mal_ubicadas": carpetas_mal_ubicadas,
            "carpetas_completas": carpetas_completas,
        },
        "carpetas_auditadas": auditorias_filtradas,
        "mensaje": (
            f"Auditoría completada sobre {len(auditorias)} carpeta(s): "
            f"{len(carpetas_sin_xml)} sin XML, "
            f"{len(carpetas_con_xml_sin_apoyo)} con XML sin soporte PDF/TXT, "
            f"{len(carpetas_sin_reporte_excel)} pendientes de reporte Excel."
        ),
    }


def _asegurar_ruta_carpeta_destino(
    cliente: Any,
    ruta_destino: str,
    carpeta_raiz_id: str,
) -> dict[str, Any]:
    """Resuelve una carpeta destino o crea las subcarpetas necesarias dentro del contenedor principal."""
    try:
        destino = resolver_ruta_drive(cliente, ruta_destino, carpeta_raiz_id=carpeta_raiz_id)
        if not destino["es_carpeta"]:
            raise ValueError(
                f"El destino '{ruta_destino}' es un archivo, no una carpeta."
            )
        return destino
    except ValueError:
        # Si no existe aún (ej. 'DOCUMENTOS ENTRADA/18-03-2026'), crear la jerarquía
        resultado_creacion = crear_carpeta_por_ruta(
            ruta_nueva_carpeta=ruta_destino,
            cliente=cliente,
            carpeta_raiz_id=carpeta_raiz_id,
        )
        return {
            "id": resultado_creacion["carpeta_id"],
            "nombre": resultado_creacion["nombre"],
            "mimeType": MIME_CARPETA,
            "es_carpeta": True,
            "padre_id": resultado_creacion["padre_id"],
            "ruta_completa": resultado_creacion["ruta_completa"],
        }


def mover_elemento_por_ruta(
    ruta_origen: str,
    ruta_destino: str,
    cliente: Any | None = None,
    carpeta_raiz_id: str | None = None,
) -> dict[str, Any]:
    """
    Mueve una carpeta o archivo específico desde `ruta_origen` hacia la carpeta `ruta_destino`.

    Si se mueve una carpeta y en el destino ya existe una carpeta homónima, fusiona su contenido
    y envía a la papelera la carpeta origen vacía para evitar duplicados.
    """
    cliente = cliente or crear_cliente_drive()
    raiz_id = carpeta_raiz_id or settings.google_drive_folder_id
    if not raiz_id:
        raise GoogleDriveConfigError("Falta GOOGLE_DRIVE_FOLDER_ID")

    if not ruta_origen or not ruta_origen.strip():
        raise ValueError("Debes indicar 'ruta_origen' del archivo o carpeta que deseas mover.")
    if not ruta_destino or not ruta_destino.strip():
        raise ValueError("Debes indicar 'ruta_destino' (la carpeta hacia donde se moverá).")

    destino = _asegurar_ruta_carpeta_destino(cliente, ruta_destino, carpeta_raiz_id=raiz_id)
    origen = resolver_ruta_drive(
        cliente,
        ruta_origen,
        carpeta_raiz_id=raiz_id,
        excluir_padre_id=destino["id"],
    )

    if origen["id"] == destino["id"]:
        return {
            "ok": True,
            "tipo": "mover_elemento",
            "movido": False,
            "origen": origen["ruta_completa"],
            "destino": destino["ruta_completa"],
            "mensaje": f"El elemento '{origen['nombre']}' ya es la misma carpeta destino.",
        }

    if origen["padre_id"] == destino["id"]:
        return {
            "ok": True,
            "tipo": "mover_elemento",
            "movido": False,
            "origen": origen["ruta_completa"],
            "destino": destino["ruta_completa"],
            "mensaje": f"'{origen['nombre']}' ya se encuentra dentro de '{destino['ruta_completa']}'.",
        }

    # Si es carpeta y ya existe una carpeta con el mismo nombre en destino, fusionar contenidos
    if origen["es_carpeta"]:
        carpeta_homonima_id = buscar_carpeta_hija(cliente, origen["nombre"], destino["id"])
        if carpeta_homonima_id and carpeta_homonima_id != origen["id"]:
            hijos_origen = _listar_hijos(cliente, origen["id"])
            for hijo in hijos_origen:
                mover_archivo(
                    cliente,
                    hijo["id"],
                    carpeta_homonima_id,
                    carpeta_origen_id=origen["id"],
                )
            eliminar_archivo(cliente, origen["id"])
            nueva_ruta = f"{destino['ruta_completa']}/{origen['nombre']}"
            return {
                "ok": True,
                "tipo": "mover_elemento",
                "movido": True,
                "fusionado_en_existente": True,
                "elemento": origen["nombre"],
                "origen_anterior": origen["ruta_completa"],
                "nueva_ruta": nueva_ruta,
                "mensaje": (
                    f"Se movió y fusionó el contenido de '{origen['ruta_completa']}' "
                    f"hacia '{nueva_ruta}'."
                ),
            }

    mover_archivo(
        cliente,
        origen["id"],
        destino["id"],
        carpeta_origen_id=origen["padre_id"],
    )
    nueva_ruta = f"{destino['ruta_completa']}/{origen['nombre']}"
    return {
        "ok": True,
        "tipo": "mover_elemento",
        "movido": True,
        "fusionado_en_existente": False,
        "elemento": origen["nombre"],
        "origen_anterior": origen["ruta_completa"],
        "nueva_ruta": nueva_ruta,
        "mensaje": f"Se movió '{origen['ruta_completa']}' hacia '{destino['ruta_completa']}'.",
    }


def crear_carpeta_por_ruta(
    ruta_nueva_carpeta: str,
    cliente: Any | None = None,
    carpeta_raiz_id: str | None = None,
) -> dict[str, Any]:
    """
    Crea una nueva carpeta en la ruta indicada dentro de Google Drive.

    Si solo se proporciona el nombre de la carpeta (ej. '25-03-2026') sin contenedor padre,
    se crea por defecto dentro de 'ENTRADAS AL INVENTARIO'.
    """
    cliente = cliente or crear_cliente_drive()
    raiz_id = carpeta_raiz_id or settings.google_drive_folder_id
    if not raiz_id:
        raise GoogleDriveConfigError("Falta GOOGLE_DRIVE_FOLDER_ID")

    ruta_limpia = (ruta_nueva_carpeta or "").strip().strip("/")
    if not ruta_limpia:
        raise ValueError("Debes indicar el nombre o ruta de la carpeta que deseas crear.")

    segmentos = [seg.strip() for seg in ruta_limpia.split("/") if seg.strip()]
    if segmentos and segmentos[0].casefold() in ALIAS_RAIZ:
        segmentos = segmentos[1:]
        crear_en_raiz = True
    else:
        crear_en_raiz = False

    if not segmentos:
        raise ValueError("La ruta proporcionada no contiene un nombre de carpeta válido.")

    segmentos[0] = _normalizar_segmento_contenedor(segmentos[0])

    # Si solo dieron un nombre simple (ej. '25-03-2026') y no pidieron raíz explícitamente,
    # ubicarlo bajo ENTRADAS AL INVENTARIO por convención del negocio.
    if (
        len(segmentos) == 1
        and not crear_en_raiz
        and segmentos[0] not in {CARPETA_ENTRADAS_AL_INVENTARIO, CARPETA_REPORTES_HISTORICOS}
    ):
        segmentos = [CARPETA_ENTRADAS_AL_INVENTARIO, segmentos[0]]

    padre_actual_id = raiz_id
    partes_creadas: list[str] = []
    ya_existia_final = True

    for indice, nombre_seg in enumerate(segmentos):
        es_ultimo = indice == len(segmentos) - 1
        existente_id = buscar_carpeta_hija(cliente, nombre_seg, padre_actual_id)
        if existente_id:
            padre_actual_id = existente_id
            partes_creadas.append(nombre_seg)
        else:
            if es_ultimo:
                ya_existia_final = False
            padre_actual_id = buscar_o_crear_carpeta(cliente, nombre_seg, padre_actual_id)
            partes_creadas.append(nombre_seg)

    ruta_completa = "/".join(partes_creadas)
    return {
        "ok": True,
        "tipo": "crear_carpeta",
        "creada": not ya_existia_final,
        "ya_existia": ya_existia_final,
        "carpeta_id": padre_actual_id,
        "nombre": partes_creadas[-1],
        "padre_id": raiz_id if len(partes_creadas) == 1 else None,
        "ruta_completa": ruta_completa,
        "mensaje": (
            f"La carpeta '{ruta_completa}' ya existía en Google Drive."
            if ya_existia_final
            else f"Se creó la carpeta '{ruta_completa}' exitosamente en Google Drive."
        ),
    }


def eliminar_elemento_por_ruta(
    ruta_objetivo: str,
    confirmar_eliminar_con_contenido: bool = False,
    cliente: Any | None = None,
    carpeta_raiz_id: str | None = None,
) -> dict[str, Any]:
    """
    Envía a la papelera de Google Drive una carpeta o archivo específico.

    Reglas de seguridad:
    1. Nunca permite eliminar las carpetas principales ('ENTRADAS AL INVENTARIO' ni 'DOCUMENTOS ENTRADA').
    2. Si el objetivo es una carpeta vacía o un archivo individual, lo elimina directamente.
    3. Si el objetivo es una carpeta con archivos o subcarpetas adentro y
       `confirmar_eliminar_con_contenido=False`, bloquea la acción y devuelve la lista
       de archivos encontrados para pedir confirmación al usuario.
    """
    cliente = cliente or crear_cliente_drive()
    raiz_id = carpeta_raiz_id or settings.google_drive_folder_id
    if not raiz_id:
        raise GoogleDriveConfigError("Falta GOOGLE_DRIVE_FOLDER_ID")

    if not ruta_objetivo or not ruta_objetivo.strip():
        raise ValueError("Debes indicar 'ruta_objetivo' de la carpeta o archivo a eliminar.")

    objetivo = resolver_ruta_drive(cliente, ruta_objetivo, carpeta_raiz_id=raiz_id)

    if objetivo["id"] == raiz_id or objetivo["nombre"] in {
        CARPETA_ENTRADAS_AL_INVENTARIO,
        CARPETA_REPORTES_HISTORICOS,
    }:
        return {
            "ok": False,
            "tipo": "eliminar_elemento",
            "eliminado": False,
            "ruta_objetivo": objetivo["ruta_completa"],
            "mensaje": (
                f"No está permitido eliminar la carpeta principal del sistema '{objetivo['nombre']}'."
            ),
        }

    if objetivo["es_carpeta"]:
        contenido_interno = _listar_hijos(cliente, objetivo["id"])
        nombres_internos = sorted(
            [item.get("name", "") for item in contenido_interno],
            key=str.casefold,
        )
        if nombres_internos and not confirmar_eliminar_con_contenido:
            return {
                "ok": False,
                "requiere_confirmacion": True,
                "tipo": "eliminar_elemento",
                "eliminado": False,
                "ruta_objetivo": objetivo["ruta_completa"],
                "total_elementos_internos": len(nombres_internos),
                "archivos_encontrados": nombres_internos,
                "mensaje": (
                    f"La carpeta '{objetivo['ruta_completa']}' contiene {len(nombres_internos)} "
                    f"elemento(s): {', '.join(nombres_internos[:10])}. "
                    "Solicita confirmación al usuario antes de eliminar una carpeta con contenido."
                ),
            }

    eliminar_archivo(cliente, objetivo["id"])
    return {
        "ok": True,
        "tipo": "eliminar_elemento",
        "eliminado": True,
        "elemento": objetivo["nombre"],
        "ruta_eliminada": objetivo["ruta_completa"],
        "es_carpeta": objetivo["es_carpeta"],
        "mensaje": (
            f"Se envió '{objetivo['ruta_completa']}' a la papelera de Google Drive."
        ),
    }


def inspeccionar_xml_drive(
    carpeta_o_archivo: str,
    cliente: Any | None = None,
    carpeta_raiz_id: str | None = None,
) -> dict[str, Any]:
    """
    Lee en modo solo lectura los metadatos y conceptos de los archivos XML en una carpeta o ruta de Google Drive.

    No modifica carpetas, no cambia el estado de sincronización ni genera reportes.
    """
    cliente = cliente or crear_cliente_drive()
    raiz_id = carpeta_raiz_id or settings.google_drive_folder_id
    if not raiz_id:
        raise GoogleDriveConfigError("Falta GOOGLE_DRIVE_FOLDER_ID")

    if not carpeta_o_archivo or not carpeta_o_archivo.strip():
        raise ValueError(
            "Debes indicar la carpeta, fecha o nombre del archivo XML que deseas inspeccionar."
        )

    objetivo = resolver_ruta_drive(cliente, carpeta_o_archivo.strip(), carpeta_raiz_id=raiz_id)
    archivos_xml_drive: list[tuple[dict[str, Any], str]] = []

    if not objetivo["es_carpeta"]:
        if Path(objetivo["nombre"]).suffix.lower() != ".xml":
            raise ValueError(
                f"El archivo '{objetivo['ruta_completa']}' no es un archivo XML."
            )
        archivos_xml_drive.append(
            (
                {
                    "id": objetivo["id"],
                    "name": objetivo["nombre"],
                    "mimeType": objetivo.get("mimeType", "text/xml"),
                },
                objetivo["padre_id"] or raiz_id,
            )
        )
    else:
        hijos = _listar_hijos(cliente, objetivo["id"])
        for h in hijos:
            if (
                h.get("mimeType") != MIME_CARPETA
                and Path(h.get("name", "")).suffix.lower() == ".xml"
                and not es_archivo_generado(h.get("name", ""))
            ):
                archivos_xml_drive.append((h, objetivo["id"]))

        # Si están organizados dentro de subcarpetas de proveedor, buscar un nivel abajo
        if not archivos_xml_drive:
            for sub in hijos:
                if sub.get("mimeType") == MIME_CARPETA:
                    for nieto in _listar_hijos(cliente, sub["id"]):
                        if (
                            nieto.get("mimeType") != MIME_CARPETA
                            and Path(nieto.get("name", "")).suffix.lower() == ".xml"
                            and not es_archivo_generado(nieto.get("name", ""))
                        ):
                            archivos_xml_drive.append((nieto, sub["id"]))

    if not archivos_xml_drive:
        return {
            "ok": True,
            "tipo": "inspeccionar_xml",
            "ruta_consultada": objetivo["ruta_completa"],
            "total_xml": 0,
            "facturas": [],
            "mensaje": f"No se encontraron archivos XML dentro de '{objetivo['ruta_completa']}'.",
        }

    facturas_detalle: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="flucito_inspeccion_xml_") as temp_dir:
        raiz_temp = Path(temp_dir)
        for indice, (item_xml, padre_id) in enumerate(archivos_xml_drive):
            nombre_xml = item_xml.get("name", f"factura_{indice}.xml")
            ruta_local = raiz_temp / f"{indice}_{Path(nombre_xml).name}"
            archivo_obj = DriveArchivo(
                id=item_xml["id"],
                nombre=nombre_xml,
                mime_type=item_xml.get("mimeType", "text/xml"),
                modificado=item_xml.get("modifiedTime", ""),
                carpeta_id=padre_id,
            )
            descargar_archivo(cliente, archivo_obj, ruta_local)
            meta = extractor.leer_meta(str(ruta_local))
            conceptos_raw = extractor.extraer_conceptos(str(ruta_local))

            moneda = (
                str(conceptos_raw[0].get("moneda") or "MXN")
                if conceptos_raw
                else "MXN"
            )
            subtotal_estimado = round(
                sum(
                    (
                        float(c["importe"])
                        if c.get("importe") is not None
                        else float(c.get("cantidad") or 1.0)
                        * float(c.get("valor_unitario") or 0.0)
                    )
                    - float(c.get("descuento") or 0.0)
                    for c in conceptos_raw
                ),
                2,
            )
            conceptos_resumen = [
                {
                    "no_identificacion": c.get("no_identificacion"),
                    "descripcion": c.get("descripcion"),
                    "cantidad": c.get("cantidad"),
                    "clave_unidad": c.get("clave_unidad"),
                    "clave_prod_serv": c.get("clave_prod_serv"),
                    "valor_unitario": c.get("valor_unitario"),
                    "descuento": c.get("descuento"),
                    "importe": (
                        c.get("importe")
                        if c.get("importe") is not None
                        else round(
                            float(c.get("cantidad") or 1.0)
                            * float(c.get("valor_unitario") or 0.0)
                            - float(c.get("descuento") or 0.0),
                            2,
                        )
                    ),
                }
                for c in conceptos_raw[:30]
            ]
            facturas_detalle.append(
                {
                    "archivo": nombre_xml,
                    "proveedor": meta.get("proveedor_nombre") or "Proveedor desconocido",
                    "rfc_proveedor": meta.get("rfc"),
                    "folio": meta.get("folio"),
                    "fecha_factura": meta.get("fecha")
                    or (conceptos_raw[0].get("fecha_compra") if conceptos_raw else None),
                    "moneda": moneda,
                    "total_conceptos": len(conceptos_raw),
                    "subtotal_estimado": subtotal_estimado,
                    "conceptos": conceptos_resumen,
                }
            )

    return {
        "ok": True,
        "tipo": "inspeccionar_xml",
        "ruta_consultada": objetivo["ruta_completa"],
        "total_xml": len(facturas_detalle),
        "facturas": facturas_detalle,
        "mensaje": (
            f"Se inspeccionaron {len(facturas_detalle)} factura(s) XML en '{objetivo['ruta_completa']}'."
        ),
    }


__all__ = [
    "resolver_ruta_drive",
    "explorar_estructura_drive",
    "auditar_facturas_drive",
    "inspeccionar_xml_drive",
    "mover_elemento_por_ruta",
    "crear_carpeta_por_ruta",
    "eliminar_elemento_por_ruta",
]
