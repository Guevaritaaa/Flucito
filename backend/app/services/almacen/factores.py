"""Catálogo de factores de precios, autocorrección de líneas y detección de rollos/metros."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from app.services.almacen.extractor import CARPETA_DATOS

logger = logging.getLogger(__name__)

_RUTA_FACTORES_DEFAULT = CARPETA_DATOS / "FACTORES_PERSONALIZADOS.json"
RUTA_FACTORES_PERSONALIZADOS = _RUTA_FACTORES_DEFAULT
SIN_FACTOR = "SIN_FACTOR"

COLUMNAS_FACTORES: tuple[str, ...] = (
    "PUBLICO",
    "MINIMO",
    "MOSTRADOR",
    "MAYOREO",
    "DISTRIBUIDOR",
)

# 8 factores oficiales de FACTORES DE PRECIO.xlsx (con erratas de tipeo corregidas).
# {COSTEO} se reemplaza por S{fila} (Precio Compra) y {PUBLICO} por T{fila} (Precio Público/Lista).
CATALOGO_FACTORES: dict[str, dict[str, str]] = {
    "COMPRAS GENERALES LOCALES": {
        "PUBLICO": "{COSTEO}*2",
        "MINIMO": "{COSTEO}/0.8",
        "MOSTRADOR": "{COSTEO}/0.7",
        "MAYOREO": "{COSTEO}/.75",
        "DISTRIBUIDOR": "{COSTEO}/0.8",
    },
    "COMPRAS GENERALES FORANEAS": {
        "PUBLICO": "{COSTEO}/0.9*2",
        "MINIMO": "{COSTEO}/0.9/0.8",
        "MOSTRADOR": "{COSTEO}/0.9/0.7",
        "MAYOREO": "{COSTEO}/0.9/0.75",
        "DISTRIBUIDOR": "{COSTEO}/0.9/0.8",
    },
    "COMPRAS ESPECIFICAS FORANEAS": {
        "PUBLICO": "{COSTEO}/0.9*2",
        "MINIMO": "{COSTEO}/0.9/0.8",
        "MOSTRADOR": "{COSTEO}/0.9/0.6",
        "MAYOREO": "{COSTEO}/0.9/0.7",
        "DISTRIBUIDOR": "{COSTEO}/0.9/0.8",
    },
    "SELLOS": {
        "PUBLICO": "{COSTEO}/0.7*4",
        "MINIMO": "{COSTEO}/0.6",
        "MOSTRADOR": "{COSTEO}/0.7*3",
        "MAYOREO": "{COSTEO}/0.7*2",
        "DISTRIBUIDOR": "{COSTEO}/0.5",
    },
    "YPC": {
        "PUBLICO": "{COSTEO}/.6",
        "MINIMO": "({COSTEO}/.6)*.8",
        "MOSTRADOR": "{COSTEO}/.6",
        "MAYOREO": "({COSTEO}/.6)*.9",
        "DISTRIBUIDOR": "({COSTEO}/.6)*.8",
    },
    "FESTO": {
        "PUBLICO": "{COSTEO}/.7",
        "MINIMO": "{COSTEO}/.9",
        "MOSTRADOR": "{COSTEO}/.7",
        "MAYOREO": "{COSTEO}/.8",
        "DISTRIBUIDOR": "{COSTEO}/.9",
    },
    "ABB": {
        "PUBLICO": "{COSTEO}*2",
        "MINIMO": "{COSTEO}/0.8",
        "MOSTRADOR": "{COSTEO}/0.7",
        "MAYOREO": "{COSTEO}/.75",
        "DISTRIBUIDOR": "{COSTEO}/0.8",
    },
    "CYBERMATIC": {
        "PUBLICO": "{COSTEO}/.9*2",
        "MINIMO": "{PUBLICO}*.8",
        "MOSTRADOR": "{PUBLICO}",
        "MAYOREO": "{PUBLICO}*.9",
        "DISTRIBUIDOR": "{PUBLICO}*.8",
    },
}

# 76 líneas registradas en Aspel SAE (de la pestaña LINEAS de FACTORES DE PRECIO.xlsx).
CATALOGO_LINEAS_BASE: dict[str, dict[str, str | None]] = {
    "YPC": {"descripcion": "YPC DE MEXICO", "factor": "YPC"},
    "PKRN": {"descripcion": "PARKER AUTOMATIZACIO", "factor": "COMPRAS GENERALES FORANEAS"},
    "PKRH": {"descripcion": "PARKER HIDRAULICA", "factor": "COMPRAS GENERALES FORANEAS"},
    "PKRFC": {"descripcion": "PARKER FLUID CONECT", "factor": "COMPRAS GENERALES FORANEAS"},
    "PKCIC": {"descripcion": "PARKER CIC", "factor": "COMPRAS GENERALES FORANEAS"},
    "FESTO": {"descripcion": "FESTO PNEUMATICS", "factor": "FESTO"},
    "SELLO": {"descripcion": "SELLADO", "factor": "SELLOS"},
    "ROSHF": {"descripcion": "ROSHFRANS", "factor": "COMPRAS GENERALES LOCALES"},
    "DAYCO": {"descripcion": "DAYCO", "factor": None},
    "QUAKE": {"descripcion": "QUAKER", "factor": "COMPRAS GENERALES LOCALES"},
    "SHELL": {"descripcion": "SHELL", "factor": "COMPRAS GENERALES LOCALES"},
    "FANDE": {"descripcion": "FANDELI", "factor": None},
    "ADCCO": {"descripcion": "ADCCOM", "factor": "COMPRAS GENERALES FORANEAS"},
    "PVC": {"descripcion": "PVC", "factor": "COMPRAS GENERALES LOCALES"},
    "GALV": {"descripcion": "GALVANIZADO", "factor": "COMPRAS GENERALES FORANEAS"},
    "NEGRO": {"descripcion": "NEGRO", "factor": "COMPRAS GENERALES FORANEAS"},
    "SMC": {"descripcion": "SMC", "factor": "COMPRAS GENERALES LOCALES"},
    "FERR": {"descripcion": "FERRETERIA", "factor": "COMPRAS GENERALES LOCALES"},
    "INOX": {"descripcion": "INOXIDABLE", "factor": "COMPRAS GENERALES FORANEAS"},
    "SURTE": {"descripcion": "SURTEK", "factor": None},
    "VALVO": {"descripcion": "VALVOLINE", "factor": None},
    "DIXON": {"descripcion": "DIXON", "factor": "COMPRAS GENERALES LOCALES"},
    "MANUL": {"descripcion": "MANULI", "factor": None},
    "PKRID": {"descripcion": "PARKER DENISON", "factor": "COMPRAS GENERALES FORANEAS"},
    "PKSK": {"descripcion": "PARKER SKINNER", "factor": "COMPRAS GENERALES FORANEAS"},
    "PKRF": {"descripcion": "PARKER FILTRACION", "factor": "COMPRAS GENERALES FORANEAS"},
    "PKRSE": {"descripcion": "PARKER SCEM EUROPA", "factor": "COMPRAS GENERALES FORANEAS"},
    "WURTH": {"descripcion": "WURTH", "factor": "COMPRAS GENERALES LOCALES"},
    "PINST": {"descripcion": "INSTRUMENTACION", "factor": "COMPRAS GENERALES LOCALES"},
    "VARIO": {"descripcion": "VARIOS", "factor": "COMPRAS GENERALES LOCALES"},
    "CESMA": {"descripcion": "CESMA MAQUINADOS", "factor": "COMPRAS GENERALES FORANEAS"},
    "GENEB": {"descripcion": "GENEBRE", "factor": "COMPRAS GENERALES FORANEAS"},
    "GATES": {"descripcion": "GATES", "factor": "COMPRAS GENERALES LOCALES"},
    "ASCO": {"descripcion": "ASCO EMERSON", "factor": "COMPRAS GENERALES FORANEAS"},
    "NUMAT": {"descripcion": "NUMATICS", "factor": "COMPRAS GENERALES LOCALES"},
    "ABB": {"descripcion": "ABB", "factor": "ABB"},
    "WORCE": {"descripcion": "WORCESTER", "factor": "COMPRAS GENERALES FORANEAS"},
    "INST": {"descripcion": "INSTRUTEK", "factor": "COMPRAS GENERALES FORANEAS"},
    "NACOB": {"descripcion": "NACOBRE", "factor": None},
    "ALFAG": {"descripcion": "ALFAGOMA", "factor": "COMPRAS GENERALES FORANEAS"},
    "TAMTO": {"descripcion": "TAMTO", "factor": "COMPRAS GENERALES FORANEAS"},
    "KAPET": {"descripcion": "KAPET HIDRAULICA", "factor": "COMPRAS GENERALES FORANEAS"},
    "DEWIT": {"descripcion": "MANOMETROS DEWIT", "factor": "COMPRAS GENERALES FORANEAS"},
    "WINTE": {"descripcion": "WINTEK", "factor": "COMPRAS GENERALES LOCALES"},
    "TRUPE": {"descripcion": "TRUPER", "factor": "COMPRAS GENERALES LOCALES"},
    "PLACJ": {"descripcion": "PLASTICOS CJ", "factor": "COMPRAS GENERALES FORANEAS"},
    "LTH": {"descripcion": "ACEITES LTH", "factor": "COMPRAS GENERALES LOCALES"},
    "ENPA": {"descripcion": "ENPA", "factor": "COMPRAS GENERALES FORANEAS"},
    "KURIY": {"descripcion": "KURIYAMA", "factor": None},
    "CLAMP": {"descripcion": "CLAMP SANITARIO INOX", "factor": "COMPRAS GENERALES FORANEAS"},
    "UF": {"descripcion": "UNIVERSAL FITTINGS", "factor": "COMPRAS GENERALES FORANEAS"},
    "VBC": {"descripcion": "VALVULA BOLA", "factor": None},
    "LYZKY": {"descripcion": "LYZKY HID", "factor": "COMPRAS GENERALES FORANEAS"},
    "HMM": {"descripcion": "HOSEMART", "factor": "COMPRAS GENERALES FORANEAS"},
    "HCA": {"descripcion": "HIDRAULICA VARIOS", "factor": None},
    "WATSO": {"descripcion": "WATSON MCDANIEL", "factor": "COMPRAS GENERALES FORANEAS"},
    "NEUMG": {"descripcion": "NEUMATICA GENERAL", "factor": "COMPRAS GENERALES FORANEAS"},
    "MILWA": {"descripcion": "MILWAUKEE", "factor": "COMPRAS GENERALES FORANEAS"},
    "URREA": {"descripcion": "URREA", "factor": None},
    "AIRTA": {"descripcion": "AIRTAC", "factor": "COMPRAS GENERALES FORANEAS"},
    "LCK": {"descripcion": "LOOK", "factor": None},
    "ALTAM": {"descripcion": "ALTAMIRA", "factor": "COMPRAS GENERALES LOCALES"},
    "CYB": {"descripcion": "CYBERMATIC", "factor": "CYBERMATIC"},
    "LOCTI": {"descripcion": "LOCTITE", "factor": "COMPRAS GENERALES LOCALES"},
    "CHINT": {"descripcion": "CHINT", "factor": None},
    "AUTOM": {"descripcion": "AUTOMATIZACION", "factor": None},
    "HTBB": {"descripcion": "HT BEST BRANDS", "factor": "COMPRAS GENERALES LOCALES"},
    "HTM": {"descripcion": "HTM", "factor": None},
    "TERMO": {"descripcion": "TERMOMETROS", "factor": "COMPRAS GENERALES FORANEAS"},
    "VM": {"descripcion": "VALVULAS MILLER", "factor": None},
    "AB": {"descripcion": "ALLEN BRADLEY", "factor": None},
    "MANOM": {"descripcion": "MANOMETROS", "factor": None},
    "DANFO": {"descripcion": "DANFOSS", "factor": None},
    "VARHD": {"descripcion": "VARIOS HIDRAULICA", "factor": "COMPRAS GENERALES FORANEAS"},
    "VAREL": {"descripcion": "VARIOS ELECTRICA", "factor": "COMPRAS GENERALES FORANEAS"},
    "VARNE": {"descripcion": "VARIOS NEUMATICA", "factor": "COMPRAS GENERALES FORANEAS"},
}

# Líneas adicionales presentes en CLIN02 de SAE90EMPRE02.FDB (se integran en obtener_catalogo_lineas
# conservando las 76 entradas originales de CATALOGO_LINEAS_BASE).
CATALOGO_LINEAS_SAE_EXTRA: dict[str, dict[str, str | None]] = {
    "CYBER": {"descripcion": "CYBERMATIC", "factor": "CYBERMATIC"},
    "MYPC": {"descripcion": "MANGUERA YPC", "factor": None},
    "ACERN": {"descripcion": "ACERO NEGRO", "factor": None},
}

ALIAS_CODIGOS_LINEA: dict[str, str] = {
    "KRUIY": "KURIY",
    "BAN": "BANDA",
}

PALABRAS_CLAVE_PREFIJO: dict[str, tuple[str, ...]] = {
    "PKRN": ("AUTOMATIZ", "NEUMAT", "SOLENOIDE", "CILINDRO"),
    "PKRH": ("HIDRAUL", "BOMBA", "MOTOR HID"),
    "PKRFC": ("FLUID", "CONECT", "MANGUERA", "CONEX", "COPLE", "ESPIGA", "FERULA"),
    "PKRID": ("DENISON",),
    "PKRF": ("FILTR", "ELEMENTO"),
    "PKRSE": ("SCEM", "EUROPA"),
    "VARHD": ("HIDRAUL",),
    "VAREL": ("ELECTR", "CABLE", "CONTACTOR", "RELEVADOR"),
    "VARNE": ("NEUMAT", "AIRE", "CONECTOR RAPIDO"),
    "VARIO": ("VARIOS",),
    "MANUL": ("MANULI", "MANGUERA", "CONEX", "FERULA"),
    "MANOM": ("MANOMETR", "GLICERINA", "PSI", "BAR"),
}

_RE_METROS_PARENTESIS = re.compile(
    r"\(\s*(\d+(?:\.\d+)?)\s*(?:m|mt|mts|metro|metros)\s*\)",
    re.IGNORECASE,
)
_RE_METROS_EXPLICITO = re.compile(
    r"\b(\d+(?:\.\d+)?)\s*(?:mt|mts|metro|metros)\b",
    re.IGNORECASE,
)
_RE_METROS_CONTEXTO = re.compile(
    r"(?:rollo|carrete|tramo|bobina)\s+(?:de\s+|x\s*)?(\d+(?:\.\d+)?)\s*m\b(?!m)",
    re.IGNORECASE,
)


def cargar_factores_personalizados(
    ruta: Path | None = None,
    *,
    incluir_bd: bool | None = None,
) -> dict[str, dict[str, str | None]]:
    """Lee los factores personalizados desde archivo JSON y desde la tabla factores_linea."""
    archivo = ruta or RUTA_FACTORES_PERSONALIZADOS
    usar_bd = incluir_bd if incluir_bd is not None else (archivo == _RUTA_FACTORES_DEFAULT)
    resultado: dict[str, dict[str, str | None]] = {}

    if archivo.is_file():
        try:
            contenido = json.loads(archivo.read_text(encoding="utf-8"))
            if isinstance(contenido, dict):
                for clave, valor in contenido.items():
                    codigo_raw = str(clave).strip().upper()
                    codigo = ALIAS_CODIGOS_LINEA.get(codigo_raw, codigo_raw)
                    if isinstance(valor, dict):
                        resultado[codigo] = {
                            "descripcion": str(valor.get("descripcion") or "").strip(),
                            "factor": valor.get("factor"),
                        }
                    elif isinstance(valor, str):
                        resultado[codigo] = {"descripcion": "", "factor": valor}
        except (OSError, json.JSONDecodeError) as error:
            logger.warning("No se pudo leer %s: %s", archivo, error)

    if usar_bd:
        try:
            from sqlalchemy import select
            from app.core.database import SessionLocal
            from app.models.almacen import FactorLinea

            with SessionLocal() as db:
                filas = db.scalars(
                    select(FactorLinea).where(FactorLinea.es_personalizado.is_(True))
                ).all()
                for fila in filas:
                    cod = ALIAS_CODIGOS_LINEA.get(fila.clave_linea, fila.clave_linea)
                    desc_prev = resultado.get(cod, {}).get("descripcion") or ""
                    resultado[cod] = {
                        "descripcion": desc_prev,
                        "factor": fila.nombre_factor,
                    }
        except Exception as exc:
            logger.debug("Lectura de factores_linea desde BD omitida: %s", exc)

    return resultado


def guardar_factor_personalizado(
    linea: str,
    factor: str | None,
    descripcion: str = "",
    ruta: Path | None = None,
    usuario_id: int | None = None,
    *,
    sincronizar_bd: bool | None = None,
) -> None:
    """Guarda o actualiza el factor asignado a una línea en JSON y en la tabla factores_linea."""
    archivo = ruta or RUTA_FACTORES_PERSONALIZADOS
    usar_bd = sincronizar_bd if sincronizar_bd is not None else (archivo == _RUTA_FACTORES_DEFAULT)
    codigo = ALIAS_CODIGOS_LINEA.get(linea.strip().upper(), linea.strip().upper())
    if not codigo:
        return

    factor_normalizado = normalizar_eleccion_factor(factor)
    actuales = cargar_factores_personalizados(archivo, incluir_bd=False)
    desc_base = (
        CATALOGO_LINEAS_BASE.get(codigo, {}).get("descripcion")
        or CATALOGO_LINEAS_SAE_EXTRA.get(codigo, {}).get("descripcion")
        or ""
    )
    desc_final = descripcion.strip() or actuales.get(codigo, {}).get("descripcion") or desc_base

    actuales[codigo] = {
        "descripcion": str(desc_final),
        "factor": factor_normalizado,
    }
    archivo.parent.mkdir(parents=True, exist_ok=True)
    archivo.write_text(
        json.dumps(actuales, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    if usar_bd and factor_normalizado:
        try:
            from sqlalchemy import select
            from app.core.database import Base, SessionLocal, engine
            from app.models.almacen import FactorLinea

            Base.metadata.create_all(bind=engine)
            with SessionLocal() as db:
                existente = db.scalar(
                    select(FactorLinea).where(FactorLinea.clave_linea == codigo[:64])
                )
                if existente is None:
                    db.add(
                        FactorLinea(
                            clave_linea=codigo[:64],
                            nombre_factor=str(factor_normalizado)[:64],
                            es_personalizado=True,
                            actualizado_por_id=usuario_id,
                        )
                    )
                else:
                    existente.nombre_factor = str(factor_normalizado)[:64]
                    existente.es_personalizado = True
                    if usuario_id is not None:
                        existente.actualizado_por_id = usuario_id
                db.commit()
        except Exception as exc:
            logger.debug("Guardado de factor personalizado en BD omitido: %s", exc)


def obtener_catalogo_lineas(
    ruta_personalizados: Path | None = None,
) -> dict[str, dict[str, str | None]]:
    """Combina el catálogo base + líneas SAE extra con los factores personalizados guardados en JSON."""
    catalogo: dict[str, dict[str, str | None]] = {
        codigo: {"descripcion": datos["descripcion"], "factor": datos["factor"]}
        for codigo, datos in CATALOGO_LINEAS_BASE.items()
    }
    for codigo, datos in CATALOGO_LINEAS_SAE_EXTRA.items():
        if codigo not in catalogo:
            catalogo[codigo] = {"descripcion": datos["descripcion"], "factor": datos["factor"]}
    personalizados = cargar_factores_personalizados(ruta_personalizados)
    for codigo, datos in personalizados.items():
        if codigo in catalogo:
            catalogo[codigo]["factor"] = datos.get("factor")
            if datos.get("descripcion"):
                catalogo[codigo]["descripcion"] = datos["descripcion"]
        else:
            catalogo[codigo] = {
                "descripcion": datos.get("descripcion") or "",
                "factor": datos.get("factor"),
            }
    return catalogo


def normalizar_eleccion_factor(eleccion: str | int | None) -> str | None:
    """Convierte un número (1..9) o nombre de factor en la clave oficial del catálogo."""
    if eleccion is None:
        return None
    nombres = list(CATALOGO_FACTORES.keys())
    if isinstance(eleccion, int):
        if 1 <= eleccion <= len(nombres):
            return nombres[eleccion - 1]
        if eleccion == len(nombres) + 1:
            return SIN_FACTOR
        return None

    texto = str(eleccion).strip().upper()
    if not texto:
        return None

    # Si viene como "2" o "2. COMPRAS GENERALES FORANEAS"
    match_num = re.match(r"^(\d+)\b", texto)
    if match_num:
        indice = int(match_num.group(1))
        if 1 <= indice <= len(nombres):
            return nombres[indice - 1]
        if indice == len(nombres) + 1:
            return SIN_FACTOR

    if texto in {SIN_FACTOR, "SIN FACTOR", "NINGUNO", "NO", "0"}:
        return SIN_FACTOR

    if texto in CATALOGO_FACTORES:
        return texto

    for nombre in nombres:
        if nombre in texto:
            return nombre
    return None


def formatear_menu_factores() -> str:
    """Genera la lista numerada (1..9) de factores con sus fórmulas legibles."""
    lineas_menu: list[str] = []
    for indice, (nombre, formulas) in enumerate(CATALOGO_FACTORES.items(), start=1):
        resumen = (
            f"Público: {formulas['PUBLICO'].replace('{COSTEO}', 'COSTO').replace('{PUBLICO}', 'PUBLICO')}, "
            f"Mínimo: {formulas['MINIMO'].replace('{COSTEO}', 'COSTO').replace('{PUBLICO}', 'PUBLICO')}, "
            f"Mostrador: {formulas['MOSTRADOR'].replace('{COSTEO}', 'COSTO').replace('{PUBLICO}', 'PUBLICO')}, "
            f"Mayoreo: {formulas['MAYOREO'].replace('{COSTEO}', 'COSTO').replace('{PUBLICO}', 'PUBLICO')}, "
            f"Distribuidor: {formulas['DISTRIBUIDOR'].replace('{COSTEO}', 'COSTO').replace('{PUBLICO}', 'PUBLICO')}"
        )
        lineas_menu.append(f"{indice}. **{nombre}** ({resumen})")
    lineas_menu.append(f"{len(CATALOGO_FACTORES) + 1}. **Sin factor** (dejar precios en 0)")
    return "\n".join(lineas_menu)


def _desambiguar_prefijo(
    candidatos: list[str],
    catalogo: dict[str, dict[str, str | None]],
    contexto: str,
) -> str:
    """Elige la línea más adecuada cuando un código truncado coincide con varios prefijos."""
    texto = contexto.upper()
    mejor_codigo = candidatos[0]
    mejor_puntaje = -1

    for codigo in candidatos:
        puntaje = 0
        for palabra in PALABRAS_CLAVE_PREFIJO.get(codigo, ()):
            if palabra in texto:
                puntaje += 2
        desc_linea = str(catalogo.get(codigo, {}).get("descripcion") or "").upper()
        for token in desc_linea.split():
            if len(token) >= 4 and token in texto:
                puntaje += 1
        if puntaje > mejor_puntaje:
            mejor_puntaje = puntaje
            mejor_codigo = codigo

    return mejor_codigo


def resolver_linea(
    linea_raw: str | None,
    proveedor: str = "",
    descripcion: str = "",
    factores_temporales: dict[str, str | None] | None = None,
    ruta_personalizados: Path | None = None,
) -> dict[str, str | None]:
    """Normaliza el código de línea (corrigiendo truncamientos de SAE) y obtiene su factor."""
    original = str(linea_raw or "").strip().upper()
    if not original:
        return {
            "linea_original": "",
            "linea_resuelta": "",
            "descripcion_linea": "",
            "factor": None,
        }

    catalogo = obtener_catalogo_lineas(ruta_personalizados)
    codigo = ALIAS_CODIGOS_LINEA.get(original, original)

    if codigo in catalogo:
        linea_resuelta = codigo
    elif len(codigo) >= 3:
        candidatos = [clave for clave in catalogo if clave.startswith(codigo)]
        if len(candidatos) == 1:
            linea_resuelta = candidatos[0]
        elif len(candidatos) > 1:
            linea_resuelta = _desambiguar_prefijo(
                candidatos,
                catalogo,
                f"{proveedor} {descripcion}",
            )
        else:
            linea_resuelta = codigo
    else:
        linea_resuelta = codigo

    info = catalogo.get(linea_resuelta, {"descripcion": "", "factor": None})
    factor = info.get("factor")

    if factores_temporales:
        override = factores_temporales.get(linea_resuelta)
        if override is None and original in factores_temporales:
            override = factores_temporales[original]
        if override is not None:
            factor = normalizar_eleccion_factor(override)

    return {
        "linea_original": original,
        "linea_resuelta": linea_resuelta,
        "descripcion_linea": info.get("descripcion") or "",
        "factor": factor,
    }


def recuperar_clave_truncada(
    clave_apoyo: str | None,
    clave_xml: str | None,
    cve_prov: str | None = None,
    claves_usadas_lote: dict[str, str] | None = None,
) -> str:
    """
    Resuelve la Clave Artículo de Aspel SAE:
    1. Si existe coincidencia inequívoca en el Catálogo Maestro SAE (`INVE02` / `CVES_ALTER02`),
       devuelve la `CVE_ART` oficial de SAE.
    2. Si es un artículo nuevo y el TXT truncó caracteres finales que sí vienen en el XML,
       recupera la clave del XML respetando el límite `VARCHAR(16)` sin colisiones.
    """
    from app.services.almacen.catalogo_sae import (
        ajustar_clave_nueva_16_chars,
        buscar_articulo_sae,
    )

    apoyo_limpio = str(clave_apoyo or "").strip()
    xml_limpio = str(clave_xml or "").strip()

    art_sae = buscar_articulo_sae(apoyo_limpio, xml_limpio, cve_prov=cve_prov)
    if art_sae and art_sae.get("cve_art"):
        cve_oficial = str(art_sae["cve_art"]).strip()
        if claves_usadas_lote is not None:
            claves_usadas_lote.setdefault(cve_oficial.upper(), (xml_limpio or apoyo_limpio).upper())
        return cve_oficial

    if not apoyo_limpio:
        candidata = xml_limpio
    elif not xml_limpio:
        candidata = apoyo_limpio
    elif (
        len(apoyo_limpio) >= 8
        and len(xml_limpio) > len(apoyo_limpio)
        and xml_limpio.upper().startswith(apoyo_limpio.upper())
    ):
        candidata = xml_limpio
    else:
        candidata = apoyo_limpio

    clave_final, _ = ajustar_clave_nueva_16_chars(
        candidata,
        codigo_original_completo=xml_limpio or apoyo_limpio,
        claves_usadas_lote=claves_usadas_lote,
    )
    return clave_final


def detectar_rollo_metros(
    clave_unidad: str | None,
    descripcion_xml: str = "",
    descripcion_apoyo: str = "",
) -> dict[str, object]:
    """Detecta si un concepto viene en unidad XRO (rollo) y/o especifica longitud en metros."""
    unidad = str(clave_unidad or "").strip().upper()
    es_xro = unidad == "XRO"

    texto = f"{descripcion_xml} {descripcion_apoyo}".strip()
    metros: float | None = None

    for patron in (_RE_METROS_PARENTESIS, _RE_METROS_CONTEXTO, _RE_METROS_EXPLICITO):
        coincidencia = patron.search(texto)
        if coincidencia:
            try:
                valor = float(coincidencia.group(1))
                if valor > 0:
                    metros = valor
                    break
            except ValueError:
                continue

    es_rollo_o_tramo = es_xro or bool(
        re.search(r"\b(?:rollo|carrete|tramo|bobina|manguera)\b", texto, re.IGNORECASE)
        or _RE_METROS_PARENTESIS.search(texto)
    )
    requiere_confirmacion = es_xro or (metros is not None and es_rollo_o_tramo)

    return {
        "es_xro": es_xro,
        "metros": metros,
        "requiere_confirmacion": requiere_confirmacion,
    }


def _evaluar_plantilla(plantilla: str, costeo: float, publico: float = 0.0) -> float:
    """Evalúa de forma segura una plantilla aritmética de factor de precios."""
    expresion = plantilla.replace("{COSTEO}", repr(float(costeo))).replace(
        "{PUBLICO}", repr(float(publico))
    )
    return float(eval(expresion, {"__builtins__": {}}, {}))  # noqa: S307


def calcular_precios_numericos(
    factor_nombre: str | None,
    precio_compra: float | int | None,
    decimales: int = 4,
) -> dict[str, float]:
    """Calcula los 5 precios numéricos (para DataFrame y exportación TXT de Aspel SAE)."""
    ceros = {columna: 0.0 for columna in COLUMNAS_FACTORES}
    if not factor_nombre or factor_nombre == SIN_FACTOR:
        return ceros

    plantillas = CATALOGO_FACTORES.get(factor_nombre.strip().upper())
    if not plantillas or precio_compra is None:
        return ceros

    costo = float(precio_compra)
    if costo <= 0:
        return ceros

    publico_raw = _evaluar_plantilla(plantillas["PUBLICO"], costeo=costo)
    resultado: dict[str, float] = {"PUBLICO": round(publico_raw, decimales)}
    for columna in ("MINIMO", "MOSTRADOR", "MAYOREO", "DISTRIBUIDOR"):
        valor = _evaluar_plantilla(plantillas[columna], costeo=costo, publico=publico_raw)
        resultado[columna] = round(valor, decimales)
    return resultado


def _formatear_numero_formula(valor: float) -> str:
    """Formatea un número para incrustarlo limpio en una fórmula de Excel."""
    texto = f"{round(float(valor), 6):.6f}".rstrip("0").rstrip(".")
    return texto or "0"


def generar_formulas_fila(
    factor_nombre: str | None,
    fila_excel: int,
    precio_compra_bruto: float | None = None,
    divisor_metros: float | None = None,
) -> dict[str, str]:
    """Genera las fórmulas dinámicas de Excel (=S{r}..., =T{r}...) para una fila (1-indexed)."""
    formulas: dict[str, str] = {}

    if (
        precio_compra_bruto is not None
        and divisor_metros is not None
        and divisor_metros > 0
    ):
        costo_txt = _formatear_numero_formula(precio_compra_bruto)
        metros_txt = _formatear_numero_formula(divisor_metros)
        formulas["PRECIO COMPRA"] = f"={costo_txt}/{metros_txt}"

    if not factor_nombre or factor_nombre == SIN_FACTOR:
        return formulas

    plantillas = CATALOGO_FACTORES.get(factor_nombre.strip().upper())
    if not plantillas:
        return formulas

    ref_costeo = f"S{fila_excel}"
    ref_publico = f"T{fila_excel}"
    for columna, plantilla in plantillas.items():
        expresion = plantilla.replace("{COSTEO}", ref_costeo).replace("{PUBLICO}", ref_publico)
        formulas[columna] = f"={expresion}"

    return formulas
