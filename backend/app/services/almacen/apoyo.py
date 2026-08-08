"""
Datos que el CFDI no trae (LÃ­nea/familia, y la Clave ArtÃ­culo "real" de Aspel)
se sacan del PDF o TXT que Compras manda junto al XML.

El emparejamiento NO es por nombre de archivo (cada sistema nombra distinto,
con distinto padding de folio: "FAC20261827" vs "INV-FAC2026001827-...").
Se hace por el folio real que trae el propio XML (atributo Folio + aÃ±o de Fecha).
"""

from __future__ import annotations

import os
import re

import pdfplumber


PATRON_CANTIDAD = re.compile(r"^\d+\.\d{2}$")


def _normaliza(codigo: str) -> str:
    return (codigo or "").strip().upper()


def _coinciden(cod_a: str, cod_b: str) -> bool:
    a, b = _normaliza(cod_a), _normaliza(cod_b)
    if not a or not b:
        return False
    # el cÃ³digo del PDF a veces trae un sufijo extra (ej. "25KL4P05000X"
    # vs "25KL4P05000" que sale del XML) -> match por prefijo
    return a == b or a.startswith(b) or b.startswith(a)


def _extraer_year_folio(nombre_archivo: str):
    """
    De un nombre de archivo saca (aÃ±o, folio_int) a partir de la primera
    corrida larga de dÃ­gitos, sin importar el padding del folio.
    "FAC20261827.pdf"                 -> ("2026", 1827)
    "INV-FAC2026001827-MX-..."        -> ("2026", 1827)
    """
    m = re.search(r"(\d{6,})", nombre_archivo)
    if not m:
        return None
    digitos = m.group(1)
    year, folio_str = digitos[:4], digitos[4:]
    if not folio_str:
        return None
    return year, int(folio_str)


PATRON_LINEA = re.compile(r"^[A-Z]{2,6}$")  # solo letras (ADC, UF...) -> distingue de "H87" (trae dÃ­gito)


def _procesar_fila(fila) -> dict | None:
    """
    Extrae {codigo_norm, clave_articulo, linea, descripcion_corta} de una fila
    de tabla por CONTENIDO, no por posiciÃ³n fija de columna -- distintos pdf
    traen distinto nÃºmero de columnas (Makronix: 13, Universal Fittings: 17).
    """
    cant_idx = next((i for i, v in enumerate(fila)
                      if v and PATRON_CANTIDAD.match(str(v).strip())), None)
    if cant_idx is None:
        return None

    cve_art, idx_cve = None, None
    for i in range(cant_idx + 1, len(fila)):
        if fila[i] and str(fila[i]).strip():
            cve_art, idx_cve = str(fila[i]).strip(), i
            break
    if not cve_art:
        return None

    linea, idx_linea = None, idx_cve
    for i in range(idx_cve + 1, len(fila)):
        v = fila[i]
        if v and PATRON_LINEA.match(str(v).strip()):
            linea, idx_linea = str(v).strip(), i
            break

    # descripciÃ³n corta: la primera celda con texto "de verdad" (varias letras,
    # no solo un cÃ³digo) despuÃ©s de la lÃ­nea -- es la columna DescripciÃ³n del pdf
    descripcion_corta = None
    for v in fila[idx_linea + 1:]:
        texto = str(v).strip() if v else ""
        if len(texto) >= 4 and not PATRON_CANTIDAD.match(texto):
            descripcion_corta = texto
            break

    return {
        "codigo_norm": _normaliza(cve_art),
        "clave_articulo": cve_art,
        "linea": linea,
        "descripcion_corta": descripcion_corta,
    }


def _leer_desde_pdf(ruta_pdf: str) -> list:
    """Lista ordenada (mismo orden que la tabla del pdf), ver _procesar_fila."""
    datos = []
    with pdfplumber.open(ruta_pdf) as pdf:
        for page in pdf.pages:
            for tabla in page.extract_tables():
                for fila in tabla:
                    if not fila:
                        continue
                    dato = _procesar_fila(fila)
                    if dato:
                        datos.append(dato)
    return datos


def _leer_desde_txt(ruta_txt: str) -> list:
    """Fallback si no hay PDF. Menos confiable por saltos de lÃ­nea del export."""
    datos = []
    with open(ruta_txt, encoding="utf-8", errors="ignore") as f:
        for linea_txt in f:
            m = re.match(r"\s*(\d+\.\d{2})(\S{6,})", linea_txt)
            if not m:
                continue
            cve_art = m.group(2)
            resto = linea_txt[m.end():]
            m2 = re.search(r"\b([A-Z]{2,6})\b", resto)
            linea = m2.group(1) if m2 else None
            descripcion_corta = resto[m2.end():].strip() if m2 else resto.strip()
            datos.append({
                "codigo_norm": _normaliza(cve_art),
                "clave_articulo": cve_art,
                "linea": linea,
                "descripcion_corta": descripcion_corta or None,
            })
    return datos


def obtener_apoyo_por_folio(carpeta: str, year: str, folio: int) -> list:
    """
    Busca en carpeta un pdf o txt cuyo nombre corresponda al mismo (year, folio)
    del XML y devuelve la lista ordenada de productos (ver _leer_desde_pdf).
    Prioriza PDF sobre TXT si ambos existen.
    """
    candidatos = []
    for nombre in os.listdir(carpeta):
        ext = os.path.splitext(nombre)[1].lower()
        if ext not in (".pdf", ".txt"):
            continue
        yf = _extraer_year_folio(nombre)
        if yf == (year, folio):
            candidatos.append(os.path.join(carpeta, nombre))
    candidatos.sort(key=lambda p: 0 if p.lower().endswith(".pdf") else 1)

    for ruta in candidatos:
        datos = _leer_desde_pdf(ruta) if ruta.lower().endswith(".pdf") else _leer_desde_txt(ruta)
        if datos:
            return datos
    return []


def buscar_dato(apoyo: list, codigo_concepto: str) -> dict | None:
    """Empareja el cÃ³digo del concepto XML contra la lista de apoyo, por cÃ³digo."""
    for dato in apoyo:
        if _coinciden(codigo_concepto, dato["codigo_norm"]):
            return dato
    return None


__all__ = ["obtener_apoyo_por_folio", "buscar_dato"]
