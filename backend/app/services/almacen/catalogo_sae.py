"""
Motor de consulta e indexación en memoria (O(1)) del Catálogo Maestro de Aspel SAE 9.0.

Carga de forma perezosa `catalogo_sae.json` (extraído de SAE90EMPRE02.FDB: INVE02, PROV02,
CLIN02, CVES_ALTER02 y COMPC02/PAR_COMPC02) y expone funciones de resolución de claves,
líneas, descripciones y proveedores con trazabilidad de origen.
"""

from __future__ import annotations

import json
import logging
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

MAX_LEN_CVE_ART = 16
MIN_LEN_PREFIJO_TRUNCADO = 6

_DIR_BACKEND = Path(__file__).resolve().parents[3]
_RUTAS_CANDIDATAS_DEFAULT = (
    _DIR_BACKEND / "datos" / "catalogo_sae.json",
    _DIR_BACKEND / "datos" / "almacen" / "catalogo_sae.json",
)


def _compactar_codigo(codigo: str | None) -> str:
    """Elimina espacios, guiones y guiones bajos conservando barras (/) y puntos (.) de medidas."""
    if not codigo:
        return ""
    return re.sub(r"[\s\-_]+", "", str(codigo).strip().upper())


def obtener_ruta_catalogo_sae() -> Path | None:
    """Resuelve la ruta de `catalogo_sae.json` desde variable de entorno o rutas por defecto."""
    env_path = os.getenv("CATALOGO_SAE_PATH", "").strip()
    if env_path:
        ruta_env = Path(env_path)
        if ruta_env.is_file():
            return ruta_env
        logger.warning("CATALOGO_SAE_PATH configurado pero no existe el archivo: %s", ruta_env)

    for ruta in _RUTAS_CANDIDATAS_DEFAULT:
        if ruta.is_file():
            return ruta
    return None


def _cargar_raw_desde_bd() -> dict[str, Any] | None:
    """
    Intenta leer el catálogo maestro SAE desde las tablas de la base de datos.
    Devuelve None si la tabla `sae_articulos` está vacía o si ocurre un error de conexión.
    """
    try:
        from sqlalchemy import func, select
        from app.core.database import SessionLocal
        from app.models.catalogo_sae import (
            SaeArticulo,
            SaeClaveAlterna,
            SaeHistorialCompra,
            SaeLinea,
            SaeProveedor,
        )

        with SessionLocal() as db:
            total_art = db.scalar(select(func.count()).select_from(SaeArticulo)) or 0
            if total_art == 0:
                return None

            lineas = {
                fila.clave_linea: fila.descripcion
                for fila in db.scalars(select(SaeLinea)).all()
            }
            proveedores: dict[str, dict[str, Any]] = {}
            rfc_a_proveedor: dict[str, list[str]] = {}
            for prov in db.scalars(select(SaeProveedor)).all():
                proveedores[prov.clave_proveedor] = {
                    "clave": prov.clave_proveedor,
                    "nombre": prov.nombre,
                    "rfc": prov.rfc,
                }
                if prov.rfc:
                    rfc_a_proveedor.setdefault(prov.rfc.upper(), []).append(prov.clave_proveedor)

            claves_alternas: dict[str, dict[str, Any]] = {}
            for alt in db.scalars(select(SaeClaveAlterna)).all():
                claves_alternas[alt.clave_alterna] = {
                    "cve_art": alt.clave_articulo,
                    "proveedor": alt.clave_proveedor,
                }

            compras_por_proveedor: dict[str, dict[str, Any]] = {}
            for hist in db.scalars(select(SaeHistorialCompra)).all():
                try:
                    lineas_comp = json.loads(hist.lineas_compradas_json or "{}")
                except json.JSONDecodeError:
                    lineas_comp = {}
                try:
                    arts_comp = json.loads(hist.articulos_comprados_json or "[]")
                except json.JSONDecodeError:
                    arts_comp = []
                compras_por_proveedor[hist.clave_proveedor] = {
                    "lineas_compradas": lineas_comp,
                    "articulos_comprados": arts_comp,
                }

            articulos: dict[str, dict[str, Any]] = {}
            for art in db.scalars(select(SaeArticulo)).all():
                articulos[art.clave_articulo] = {
                    "cve_art": art.clave_articulo,
                    "descr": art.descripcion,
                    "linea": art.clave_linea or "",
                    "uni_med": art.unidad_entrada,
                    "cve_sat": art.cve_sat,
                    "cve_unidad": art.cve_unidad,
                }

            return {
                "origen_carga": "postgresql_db",
                "lineas": lineas,
                "proveedores": proveedores,
                "rfc_a_proveedor": rfc_a_proveedor,
                "claves_alternas": claves_alternas,
                "compras_por_proveedor": compras_por_proveedor,
                "articulos": articulos,
            }
    except Exception as exc:
        logger.debug("Respaldo a JSON para catálogo SAE (BD no disponible): %s", exc)
        return None


@lru_cache(maxsize=1)
def cargar_catalogo_sae() -> dict[str, Any]:
    """
    Carga el catálogo SAE una sola vez en RAM y construye índices O(1).
    Prioriza las tablas de la base de datos cuando están pobladas y no se forzó
    `CATALOGO_SAE_PATH`; en caso contrario utiliza `catalogo_sae.json`.
    """
    estructura_vacia: dict[str, Any] = {
        "disponible": False,
        "ruta": None,
        "lineas": {},
        "proveedores": {},
        "rfc_a_proveedor": {},
        "claves_alternas": {},
        "claves_alternas_por_prov": {},
        "compras_por_proveedor": {},
        "articulos_exactos": {},
        "articulos_compactos": {},
        "articulos_por_prefijo4": {},
    }

    env_path = os.getenv("CATALOGO_SAE_PATH", "").strip()
    raw: dict[str, Any] | None = None
    origen_str = ""

    if not env_path:
        raw = _cargar_raw_desde_bd()
        if raw is not None:
            origen_str = "database:sae_articulos"

    if raw is None:
        ruta = obtener_ruta_catalogo_sae()
        if ruta is None:
            logger.warning("No se encontró catalogo_sae.json ni datos en BD; operando con catálogo SAE vacío.")
            return estructura_vacia
        try:
            with ruta.open("r", encoding="utf-8") as fh:
                raw = json.load(fh)
            origen_str = str(ruta)
        except Exception as exc:
            logger.error("Error leyendo catalogo_sae.json en %s: %s", ruta, exc)
            return estructura_vacia

    lineas_raw: dict[str, str] = raw.get("lineas") or {}
    proveedores_raw: dict[str, dict[str, Any]] = raw.get("proveedores") or {}
    rfc_a_prov_raw: dict[str, list[str]] = raw.get("rfc_a_proveedor") or {}
    claves_alt_raw: dict[str, dict[str, Any]] = raw.get("claves_alternas") or {}
    compras_prov_raw: dict[str, dict[str, Any]] = raw.get("compras_por_proveedor") or {}
    articulos_raw: dict[str, dict[str, Any]] = raw.get("articulos") or {}

    articulos_exactos: dict[str, dict[str, Any]] = {}
    articulos_compactos: dict[str, list[str]] = {}
    articulos_por_prefijo4: dict[str, list[str]] = {}

    for cve_key, datos in articulos_raw.items():
        cve_oficial = str(datos.get("cve_art") or cve_key).strip()
        if not cve_oficial:
            continue
        cve_upper = cve_oficial.upper()
        registro = {
            "cve_art": cve_oficial,
            "linea": str(datos.get("linea") or "").strip().upper(),
            "uni_med": str(datos.get("uni_med") or "").strip(),
            "cve_sat": str(datos.get("cve_sat") or "").strip(),
            "cve_unidad": str(datos.get("cve_unidad") or "").strip(),
            "descr": str(datos.get("descr") or "").strip(),
        }
        articulos_exactos[cve_upper] = registro

        compacto = _compactar_codigo(cve_upper)
        if compacto:
            lista_comp = articulos_compactos.setdefault(compacto, [])
            if cve_upper not in lista_comp:
                lista_comp.append(cve_upper)

            if len(compacto) >= 4:
                pref4 = compacto[:4]
                lista_pref = articulos_por_prefijo4.setdefault(pref4, [])
                if cve_upper not in lista_pref:
                    lista_pref.append(cve_upper)

    claves_alternas: dict[str, list[dict[str, str]]] = {}
    claves_alternas_por_prov: dict[tuple[str, str], list[str]] = {}

    for cve_alt, info_alt in claves_alt_raw.items():
        alt_upper = str(cve_alt).strip().upper()
        if not alt_upper:
            continue
        if isinstance(info_alt, dict):
            cve_art_dest = str(info_alt.get("cve_art") or "").strip().upper()
            prov_alt = str(info_alt.get("proveedor") or "").strip()
        else:
            cve_art_dest = str(info_alt or "").strip().upper()
            prov_alt = ""

        if not cve_art_dest:
            continue

        claves_alternas.setdefault(alt_upper, []).append(
            {"cve_art": cve_art_dest, "proveedor": prov_alt}
        )
        if prov_alt:
            lista_prov = claves_alternas_por_prov.setdefault((prov_alt, alt_upper), [])
            if cve_art_dest not in lista_prov:
                lista_prov.append(cve_art_dest)

    rfc_a_proveedor: dict[str, list[str]] = {
        str(rfc).strip().upper(): [str(p).strip() for p in lista if str(p).strip()]
        for rfc, lista in rfc_a_prov_raw.items()
        if str(rfc).strip()
    }

    lineas_norm: dict[str, str] = {
        str(k).strip().upper(): str(v or "").strip()
        for k, v in lineas_raw.items()
        if str(k).strip()
    }

    proveedores_norm: dict[str, dict[str, str]] = {
        str(k).strip(): {
            "clave": str(v.get("clave") or k).strip(),
            "rfc": str(v.get("rfc") or "").strip().upper(),
            "nombre": str(v.get("nombre") or "").strip(),
        }
        for k, v in proveedores_raw.items()
        if str(k).strip()
    }

    logger.info(
        "Catálogo SAE cargado desde %s: %d artículos, %d proveedores, %d líneas, %d claves alternas.",
        origen_str,
        len(articulos_exactos),
        len(proveedores_norm),
        len(lineas_norm),
        len(claves_alternas),
    )

    return {
        "disponible": True,
        "ruta": origen_str,
        "lineas": lineas_norm,
        "proveedores": proveedores_norm,
        "rfc_a_proveedor": rfc_a_proveedor,
        "claves_alternas": claves_alternas,
        "claves_alternas_por_prov": claves_alternas_por_prov,
        "compras_por_proveedor": compras_prov_raw,
        "articulos_exactos": articulos_exactos,
        "articulos_compactos": articulos_compactos,
        "articulos_por_prefijo4": articulos_por_prefijo4,
    }


def limpiar_cache_catalogo_sae() -> None:
    """Limpia la caché en memoria del catálogo SAE (útil para pruebas automatizadas)."""
    cargar_catalogo_sae.cache_clear()


def buscar_articulo_sae(
    *codigos: str | None,
    cve_prov: str | None = None,
) -> dict[str, Any] | None:
    """
    Busca un artículo en el catálogo SAE probando una lista ordenada de códigos candidatos
    (ej. clave_apoyo del TXT/PDF, no_identificacion del XML, codigo_secundario).

    Orden de resolución:
    1. Coincidencia exacta en `INVE02` (`CVE_ART`).
    2. Coincidencia en `CVES_ALTER02` (priorizando tupla `(cve_prov, cve_alter)`).
    3. Coincidencia compacta alfanumérica en `INVE02` (solo si es única o desambiguada por otro código).
    4. Coincidencia por prefijo truncado (>= 6 caracteres) en `INVE02` (solo si es única o desambiguada).
    """
    catalogo = cargar_catalogo_sae()
    if not catalogo["disponible"]:
        return None

    articulos_exactos: dict[str, dict[str, Any]] = catalogo["articulos_exactos"]
    claves_alt_prov: dict[tuple[str, str], list[str]] = catalogo["claves_alternas_por_prov"]
    claves_alt: dict[str, list[dict[str, str]]] = catalogo["claves_alternas"]
    articulos_compactos: dict[str, list[str]] = catalogo["articulos_compactos"]
    articulos_pref4: dict[str, list[str]] = catalogo["articulos_por_prefijo4"]

    candidatos_limpios: list[str] = []
    for cod in codigos:
        if cod is None:
            continue
        texto = str(cod).strip()
        if texto and texto.upper() not in {"N/A", "NONE", "NULL", "S/N"}:
            upper = texto.upper()
            if upper not in candidatos_limpios:
                candidatos_limpios.append(upper)

    if not candidatos_limpios:
        return None

    prov_limpio = str(cve_prov).strip() if cve_prov else ""

    # 1. Coincidencia exacta en INVE02
    for cod_upper in candidatos_limpios:
        if cod_upper in articulos_exactos:
            res = dict(articulos_exactos[cod_upper])
            res["origen_clave"] = "INVE02_EXACTO"
            res["nivel_coincidencia"] = "exacta"
            res["codigo_buscado"] = cod_upper
            return res

    # 2. Coincidencia en CVES_ALTER02 (priorizando proveedor si se conoce)
    for cod_upper in candidatos_limpios:
        if prov_limpio and (prov_limpio, cod_upper) in claves_alt_prov:
            destinos = claves_alt_prov[(prov_limpio, cod_upper)]
            if len(destinos) == 1 and destinos[0] in articulos_exactos:
                res = dict(articulos_exactos[destinos[0]])
                res["origen_clave"] = "CVES_ALTER02"
                res["nivel_coincidencia"] = "clave_alterna_proveedor"
                res["proveedor_alterna"] = prov_limpio
                res["codigo_buscado"] = cod_upper
                return res

        if cod_upper in claves_alt:
            entradas = claves_alt[cod_upper]
            cves_unicas = list({e["cve_art"] for e in entradas if e["cve_art"] in articulos_exactos})
            if len(cves_unicas) == 1:
                cve_dest = cves_unicas[0]
                prov_asociado = next(
                    (e["proveedor"] for e in entradas if e["cve_art"] == cve_dest and e.get("proveedor")),
                    "",
                )
                res = dict(articulos_exactos[cve_dest])
                res["origen_clave"] = "CVES_ALTER02"
                res["nivel_coincidencia"] = "clave_alterna"
                if prov_asociado:
                    res["proveedor_alterna"] = prov_asociado
                res["codigo_buscado"] = cod_upper
                return res

    # 3. Coincidencia por clave compacta (sin guiones, puntos ni espacios)
    compactos_candidatos = [(_compactar_codigo(c), c) for c in candidatos_limpios]
    for comp, cod_upper in compactos_candidatos:
        if len(comp) < 3:
            continue
        coincidencias = articulos_compactos.get(comp, [])
        if len(coincidencias) == 1:
            cve_dest = coincidencias[0]
            res = dict(articulos_exactos[cve_dest])
            res["origen_clave"] = "INVE02_COMPACTO"
            res["nivel_coincidencia"] = "compacta_unica"
            res["codigo_buscado"] = cod_upper
            return res

    # 4. Coincidencia por prefijo (cuando el TXT truncó una clave larga de SAE)
    for comp, cod_upper in compactos_candidatos:
        if len(comp) < MIN_LEN_PREFIJO_TRUNCADO:
            continue
        pref4 = comp[:4]
        universo = articulos_pref4.get(pref4, [])
        if not universo:
            continue

        # Primero probar prefijo literal exacto sobre CVE_ART
        coincidencias_pref = [
            cve for cve in universo if cve.startswith(cod_upper)
        ]
        # Si no hubo por literal (ej. diferencias de guion), probar por compacto
        if not coincidencias_pref:
            coincidencias_pref = [
                cve for cve in universo if _compactar_codigo(cve).startswith(comp)
            ]

        if len(coincidencias_pref) == 1:
            cve_dest = coincidencias_pref[0]
            res = dict(articulos_exactos[cve_dest])
            res["origen_clave"] = "INVE02_PREFIJO_UNICO"
            res["nivel_coincidencia"] = "prefijo_unico"
            res["codigo_buscado"] = cod_upper
            return res

        # Si hay múltiples candidatos por el prefijo del TXT, ver si otro código (del XML) desambigua
        if len(coincidencias_pref) > 1 and len(compactos_candidatos) > 1:
            for otro_comp, _ in compactos_candidatos:
                if otro_comp == comp or len(otro_comp) <= len(comp):
                    continue
                desambiguados = [
                    cve
                    for cve in coincidencias_pref
                    if otro_comp.startswith(_compactar_codigo(cve))
                    or _compactar_codigo(cve).startswith(otro_comp)
                ]
                if len(desambiguados) == 1:
                    cve_dest = desambiguados[0]
                    res = dict(articulos_exactos[cve_dest])
                    res["origen_clave"] = "INVE02_PREFIJO_DESAMBIGUADO"
                    res["nivel_coincidencia"] = "prefijo_desambiguado_xml"
                    res["codigo_buscado"] = cod_upper
                    return res

    return None


def ajustar_clave_nueva_16_chars(
    clave_propuesta: str,
    codigo_original_completo: str | None = None,
    claves_usadas_lote: dict[str, str] | None = None,
) -> tuple[str, bool]:
    """
    Asegura que una clave de artículo nuevo respete el límite VARCHAR(16) de Aspel SAE
    sin colisionar con artículos existentes en `INVE02` ni con otros artículos distintos del lote.

    Devuelve `(clave_ajustada, hubo_colision_resuelta)`.
    """
    limpia = str(clave_propuesta or "").strip()
    if not limpia:
        return "", False

    original_ref = str(codigo_original_completo or limpia).strip().upper()
    catalogo = cargar_catalogo_sae()
    articulos_exactos: dict[str, dict[str, Any]] = catalogo.get("articulos_exactos") or {}

    if len(limpia) <= MAX_LEN_CVE_ART:
        if claves_usadas_lote is not None:
            claves_usadas_lote.setdefault(limpia.upper(), original_ref)
        return limpia, False

    recortada = limpia[:MAX_LEN_CVE_ART]
    recortada_upper = recortada.upper()

    colision_inve = (
        recortada_upper in articulos_exactos
        and recortada_upper != original_ref
    )
    colision_lote = (
        claves_usadas_lote is not None
        and recortada_upper in claves_usadas_lote
        and claves_usadas_lote[recortada_upper] != original_ref
    )

    if not colision_inve and not colision_lote:
        if claves_usadas_lote is not None:
            claves_usadas_lote[recortada_upper] = original_ref
        return recortada, False

    # Resolver colisión conservando los últimos caracteres diferenciadores del código original
    for sufijo_len in (3, 4, 5):
        sufijo = limpia[-sufijo_len:]
        prefijo_len = MAX_LEN_CVE_ART - sufijo_len
        candidata = f"{limpia[:prefijo_len]}{sufijo}"
        cand_upper = candidata.upper()
        en_inve = cand_upper in articulos_exactos and cand_upper != original_ref
        en_lote = (
            claves_usadas_lote is not None
            and cand_upper in claves_usadas_lote
            and claves_usadas_lote[cand_upper] != original_ref
        )
        if not en_inve and not en_lote:
            if claves_usadas_lote is not None:
                claves_usadas_lote[cand_upper] = original_ref
            logger.warning(
                "Colisión de truncamiento a 16 chars evitada para '%s': '%s' -> '%s'",
                limpia,
                recortada,
                candidata,
            )
            return candidata, True

    if claves_usadas_lote is not None:
        claves_usadas_lote[recortada_upper] = original_ref
    return recortada, True


def resolver_proveedor_sae(
    rfc: str | None,
    num_proveedor_apoyo: str | None = None,
    linea: str | None = None,
    cve_art: str | None = None,
) -> tuple[str | None, str]:
    """
    Resuelve la clave numérica de proveedor de Aspel SAE (`PROV02.CLAVE`) y su origen.

    Prioridad:
    1. Número de proveedor explícito en TXT/PDF de apoyo (`TXT_APOYO`).
    2. Proveedor registrado en `CVES_ALTER02` para el artículo (`CVES_ALTER02`).
    3. RFC del emisor en `PROV02` (`PROV02_RFC_UNICO` o desambiguado por línea/historial).
    """
    if num_proveedor_apoyo is not None and str(num_proveedor_apoyo).strip():
        return str(num_proveedor_apoyo).strip(), "TXT_APOYO"

    catalogo = cargar_catalogo_sae()
    if not catalogo["disponible"]:
        return None, "SIN_CATALOGO"

    if cve_art:
        cve_upper = str(cve_art).strip().upper()
        for entradas in catalogo["claves_alternas"].values():
            for entrada in entradas:
                if entrada.get("cve_art") == cve_upper and entrada.get("proveedor"):
                    return str(entrada["proveedor"]).strip(), "CVES_ALTER02"

    rfc_limpio = str(rfc or "").strip().upper()
    if not rfc_limpio:
        return None, "SIN_RFC"

    claves_prov = catalogo["rfc_a_proveedor"].get(rfc_limpio, [])
    if not claves_prov:
        return None, "RFC_NO_REGISTRADO"

    if len(claves_prov) == 1:
        return claves_prov[0], "PROV02_RFC_UNICO"

    # Desambiguar RFC compartido entre varias claves de proveedor (ej. Parker 2 vs 3, Kuriyama 37 vs 151)
    compras_prov: dict[str, dict[str, Any]] = catalogo["compras_por_proveedor"]
    linea_limpia = str(linea or "").strip().upper()

    if linea_limpia:
        candidatos_con_linea = [
            cp
            for cp in claves_prov
            if linea_limpia in (compras_prov.get(cp, {}).get("lineas_frecuentes") or [])
        ]
        if len(candidatos_con_linea) == 1:
            return candidatos_con_linea[0], "PROV02_RFC_LINEA"
        if len(candidatos_con_linea) > 1:
            mejor = max(
                candidatos_con_linea,
                key=lambda cp: int(compras_prov.get(cp, {}).get("total_articulos_comprados") or 0),
            )
            return mejor, "PROV02_RFC_LINEA"

    # Elegir el proveedor con historial activo de compras
    con_compras = [
        cp
        for cp in claves_prov
        if int(compras_prov.get(cp, {}).get("total_articulos_comprados") or 0) > 0
    ]
    if len(con_compras) == 1:
        return con_compras[0], "PROV02_RFC_HISTORIAL_UNICO"
    if len(con_compras) > 1:
        mejor = max(
            con_compras,
            key=lambda cp: int(compras_prov.get(cp, {}).get("total_articulos_comprados") or 0),
        )
        return mejor, "PROV02_RFC_HISTORIAL_MAYOR"

    # Desambiguación por nombre de división (ej. Parker 2 C.I.C. vs 3 M&C)
    if rfc_limpio == "PHM870907PP0" and "2" in claves_prov and "3" in claves_prov:
        if linea_limpia == "PKCIC":
            return "2", "PROV02_RFC_DIVISION"
        return "3", "PROV02_RFC_DIVISION"

    return claves_prov[0], "PROV02_RFC_PRIMERO"


def inferir_linea_por_proveedor(
    cve_prov: str | None,
    descripcion: str = "",
) -> tuple[str | None, str]:
    """
    Infiere la línea de producto (`LIN_PROD`) a partir del historial de compras del proveedor en SAE.

    Política conservadora:
    - Si el proveedor maneja una única línea histórica en SAE, la devuelve con confianza `"HISTORIAL_UNICA"`.
    - Si maneja varias líneas, solo devuelve una si la descripción del artículo menciona de forma
      inequívoca el código o nombre de una de esas líneas en `CLIN02` (`"HISTORIAL_KEYWORD"`).
    - Si existe ambigüedad entre varias líneas, devuelve `(None, "HISTORIAL_AMBIGUO")` para que
      Flucito solicite confirmación al usuario en vez de adivinar.
    """
    if not cve_prov:
        return None, "SIN_PROVEEDOR"

    catalogo = cargar_catalogo_sae()
    if not catalogo["disponible"]:
        return None, "SIN_CATALOGO"

    prov_key = str(cve_prov).strip()
    info_compras = catalogo["compras_por_proveedor"].get(prov_key)
    if not info_compras:
        return None, "SIN_HISTORIAL"

    lineas_frec: list[str] = [
        str(lin).strip().upper()
        for lin in (info_compras.get("lineas_frecuentes") or [])
        if str(lin).strip()
    ]
    if not lineas_frec:
        return None, "SIN_LINEAS_HISTORICAS"

    if len(lineas_frec) == 1:
        return lineas_frec[0], "HISTORIAL_UNICA"

    # Desambiguar usando palabras clave de la descripción contra CLIN02
    texto_desc = str(descripcion or "").upper()
    if texto_desc:
        lineas_catalogo: dict[str, str] = catalogo["lineas"]
        coincidencias: list[str] = []
        for lin in lineas_frec:
            desc_lin = str(lineas_catalogo.get(lin) or "").upper()
            tokens = [
                tok
                for tok in re.split(r"[^A-Z0-9]+", f"{lin} {desc_lin}")
                if len(tok) >= 3 and tok not in {"PARKER", "VARIOS", "PARA", "CON", "DEL", "MEXICO"}
            ]
            if any(re.search(rf"\b{re.escape(tok)}\b", texto_desc) for tok in tokens):
                coincidencias.append(lin)

        if len(coincidencias) == 1:
            return coincidencias[0], "HISTORIAL_KEYWORD"

    return None, "HISTORIAL_AMBIGUO"


def buscar_en_catalogo_sae(
    consulta: str | None = None,
    limite: int = 25,
    *,
    producto_o_clave: str | None = None,
    linea: str | None = None,
    proveedor: str | None = None,
) -> dict[str, Any]:
    """
    Realiza una búsqueda rápida en memoria sobre artículos (`INVE02`), proveedores (`PROV02`)
    y líneas (`CLIN02`) del catálogo maestro de SAE para responder consultas del usuario en el chat.
    """
    catalogo = cargar_catalogo_sae()
    nota_alcance = (
        "Datos del Catálogo Maestro de Aspel SAE (INVE02, PROV02, CLIN02, CVES_ALTER02): "
        "reflejan claves oficiales, descripciones, líneas y proveedores registrados, "
        "no existencias físicas ni stock en tiempo real."
    )
    if not catalogo["disponible"]:
        return {
            "ok": False,
            "disponible": False,
            "alcance": nota_alcance,
            "nota_alcance": nota_alcance,
            "mensaje": "El catálogo maestro de Aspel SAE (catalogo_sae.json) no está disponible.",
        }

    termino = str(consulta or producto_o_clave or proveedor or "").strip()
    filtro_linea = str(linea or "").strip().upper()
    filtro_prov = str(proveedor or "").strip().upper()
    limite = max(1, min(int(limite or 25), 100))

    linea_info = None
    if filtro_linea and filtro_linea in catalogo["lineas"]:
        linea_info = {
            "cve_lin": filtro_linea,
            "descripcion": catalogo["lineas"][filtro_linea],
        }

    if not termino and not filtro_linea and not filtro_prov:
        return {
            "ok": True,
            "disponible": True,
            "alcance": nota_alcance,
            "nota_alcance": nota_alcance,
            "resumen_catalogo": {
                "total_articulos": len(catalogo["articulos_exactos"]),
                "total_proveedores": len(catalogo["proveedores"]),
                "total_lineas": len(catalogo["lineas"]),
                "total_claves_alternas": len(catalogo["claves_alternas"]),
            },
        }

    termino_upper = termino.upper()
    termino_comp = _compactar_codigo(termino_upper) if termino_upper else ""

    # 1. Buscar en artículos (priorizando coincidencia exacta, luego prefijo de clave, luego descripción)
    exactos_art: list[dict[str, Any]] = []
    prefijo_art: list[dict[str, Any]] = []
    contenido_art: list[dict[str, Any]] = []

    art_directo = buscar_articulo_sae(termino_upper) if termino_upper else None
    cve_directa = art_directo["cve_art"].upper() if art_directo else None
    if art_directo and (not filtro_linea or art_directo.get("linea") == filtro_linea):
        exactos_art.append(art_directo)

    tokens_busqueda = [t for t in termino_upper.split() if t]

    for cve_upper, info in catalogo["articulos_exactos"].items():
        if cve_upper == cve_directa:
            continue
        lin_upper = info["linea"].upper()
        if filtro_linea and lin_upper != filtro_linea:
            continue
        if not tokens_busqueda:
            if len(contenido_art) < limite:
                contenido_art.append(info)
            continue

        descr_upper = info["descr"].upper()
        if cve_upper.startswith(termino_upper) or (
            len(termino_comp) >= 3 and _compactar_codigo(cve_upper).startswith(termino_comp)
        ):
            if len(prefijo_art) < limite:
                prefijo_art.append(info)
        elif all(
            tok in cve_upper or tok in descr_upper or tok == lin_upper
            for tok in tokens_busqueda
        ):
            if len(contenido_art) < limite:
                contenido_art.append(info)

    todos_coincidentes = exactos_art + prefijo_art + contenido_art
    articulos_encontrados = todos_coincidentes[:limite]

    # 2. Buscar en proveedores
    proveedores_encontrados: list[dict[str, Any]] = []
    compras_prov = catalogo["compras_por_proveedor"]
    tokens_prov = [t for t in (filtro_prov or termino_upper).split() if t]
    if tokens_prov or filtro_linea:
        for cve_prov, info_p in catalogo["proveedores"].items():
            hist = compras_prov.get(cve_prov, {})
            lineas_frec = hist.get("lineas_frecuentes", [])
            texto_prov = f"{cve_prov} {info_p['rfc']} {info_p['nombre']}".upper()
            coincide_tok = all(tok in texto_prov for tok in tokens_prov) if tokens_prov else True
            coincide_lin = (filtro_linea in lineas_frec) if filtro_linea and not tokens_prov else True
            if coincide_tok and coincide_lin:
                proveedores_encontrados.append(
                    {
                        **info_p,
                        "lineas_frecuentes": lineas_frec,
                        "total_articulos_comprados": hist.get("total_articulos_comprados", 0),
                    }
                )
                if len(proveedores_encontrados) >= 15:
                    break

    # 3. Buscar en líneas
    lineas_encontradas: list[dict[str, str]] = []
    termino_lin = filtro_linea or termino_upper
    if termino_lin:
        for cve_lin, desc_lin in catalogo["lineas"].items():
            if termino_lin in cve_lin or termino_lin in desc_lin.upper():
                lineas_encontradas.append({"linea": cve_lin, "descripcion": desc_lin})

    return {
        "ok": True,
        "disponible": True,
        "consulta": termino or filtro_linea,
        "linea_info": linea_info,
        "total_articulos_coincidentes": len(todos_coincidentes),
        "total_articulos_mostrados": len(articulos_encontrados),
        "articulos": articulos_encontrados,
        "proveedores": proveedores_encontrados,
        "lineas": lineas_encontradas[:15],
        "alcance": nota_alcance,
        "nota_alcance": nota_alcance,
    }


__all__ = [
    "MAX_LEN_CVE_ART",
    "ajustar_clave_nueva_16_chars",
    "buscar_articulo_sae",
    "buscar_en_catalogo_sae",
    "cargar_catalogo_sae",
    "inferir_linea_por_proveedor",
    "limpiar_cache_catalogo_sae",
    "obtener_ruta_catalogo_sae",
    "resolver_proveedor_sae",
]
