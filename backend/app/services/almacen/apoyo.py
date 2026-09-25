"""
Datos que el CFDI no trae (Línea/familia, número de proveedor y Clave Artículo de Aspel)
se sacan del PDF o TXT que Compras manda junto al XML.

El emparejamiento se hace por el folio real del XML contra:
  1. El número de COMPRA que aparece en el encabezado del TXT/PDF
  2. Si no hay encabezado, por folio como substring de los dígitos del nombre del archivo
"""

from __future__ import annotations

import logging
import os
import re

import pdfplumber


PATRON_CANTIDAD = re.compile(r"^\d+\.\d{2}$")
logger = logging.getLogger(__name__)


def _normaliza(codigo: str) -> str:
    return (codigo or "").strip().upper()


def _coinciden(cod_a: str, cod_b: str) -> bool:
    a, b = _normaliza(cod_a), _normaliza(cod_b)
    if not a or not b:
        return False
    # el código del PDF a veces trae un sufijo extra (ej. "25KL4P05000X"
    # vs "25KL4P05000" que sale del XML) -> match por prefijo
    return a == b or a.startswith(b) or b.startswith(a)


def extraer_numero_compra(texto: str) -> str | None:
    """
    Extrae el número de COMPRA del encabezado del TXT/PDF de Aspel SAE.
    Ej: "COMPRA      A33320"       -> "A33320"
        "COMPRA               23822375292"  -> "23822375292"
    """
    if not texto:
        return None
    m = re.search(r"COMPRA\s+(\S+)", texto, re.IGNORECASE)
    return m.group(1).strip() if m else None


PATRON_LINEA = re.compile(r"^[A-Z]{2,6}$")  # solo letras (ADC, UF...) -> distingue de "H87" (trae dígito)


def extraer_numero_proveedor(texto: str) -> str | None:
    """Extrae la clave/número de proveedor (ej: 463, 472) asociada a la etiqueta Proveedor."""
    if not texto:
        return None
    # Caso 1: Proveedor: ... ( 463 )
    m = re.search(r"Proveedor:?[\s\S]{0,50}?\(\s*(\d{1,6})\s*\)", texto, re.IGNORECASE)
    if m:
        return m.group(1)
    # Caso 2: ( 463 ) ... Proveedor
    m = re.search(r"\(\s*(\d{1,6})\s*\)[\s\S]{0,50}?Proveedor", texto, re.IGNORECASE)
    if m:
        return m.group(1)
    # Caso 3: Proveedor: 463 (sin paréntesis)
    m = re.search(r"Proveedor:?\s*(\d{1,6})\b", texto, re.IGNORECASE)
    if m:
        return m.group(1)
    return None


def _procesar_fila(fila) -> dict | None:
    """
    Extrae {codigo_norm, clave_articulo, linea, descripcion_corta} de una fila
    de tabla por CONTENIDO, no por posición fija de columna -- distintos pdf
    traen distinto número de columnas (Makronix: 13, Universal Fittings: 17).
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
    if not cve_art or idx_cve is None:
        return None

    linea, idx_linea = None, idx_cve
    for i in range(idx_cve + 1, len(fila)):
        v = fila[i]
        if v and PATRON_LINEA.match(str(v).strip()):
            linea, idx_linea = str(v).strip(), i
            break

    # descripción corta: la primera celda con texto "de verdad" (varias letras,
    # no solo un código) después de la línea -- es la columna Descripción del pdf
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
    num_proveedor = None
    with pdfplumber.open(ruta_pdf) as pdf:
        for page in pdf.pages:
            if not num_proveedor:
                num_proveedor = extraer_numero_proveedor(page.extract_text() or "")
            for tabla in page.extract_tables():
                for fila in tabla:
                    if not fila:
                        continue
                    dato = _procesar_fila(fila)
                    if dato:
                        datos.append(dato)

    if num_proveedor:
        for d in datos:
            d["numero_proveedor"] = num_proveedor
    return datos


# ─── Regex para el formato de columnas fijas de Aspel SAE ───────────────
# Formato de línea de producto en TXT de Aspel SAE:
#   "    10.00 CPLL04-1/8                        CYB     CODO GIRATORIO ...  3.00   13.1870   131.87"
#   "      2.009261                              FEST    HORQUILLA SGS-...   0.00  379.2000   758.40"
#   "      5.00CBPL10-1/2                        CYB     CODO BANJO ...      3.00   43.9950   219.97"
#
# Patrón:  cantidad(dd.dd) + espacio_opcional + clave_articulo + espacios + linea(2-6 letras) + descripcion + numeros_finales
PATRON_LINEA_PRODUCTO = re.compile(
    r"^\s*"
    r"(\d+\.\d{2})"          # Grupo 1: Cantidad (ej: 10.00, 2.00, 5.00)
    r"\s*"                   # Espacio opcional (a veces está pegado)
    r"(\S{3,})"              # Grupo 2: Clave artículo (ej: CPLL04-1/8, 9261, CBPL10-1/2)
    r"\s+"                   # Espacios obligatorios
    r"([A-Z]{2,6})"          # Grupo 3: Línea/familia (ej: CYB, FEST, UF)
    r"\s+"                   # Espacios obligatorios
    r"(.+?)"                 # Grupo 4: Descripción (captura lazy)
    r"\s+"                   # Espacios antes de los números finales
    r"(\d+\.\d{2})"          # Grupo 5: % Descuento
    r"\s+"
    r"([\d,.]+)"             # Grupo 6: Costo unitario
    r"\s+"
    r"([\d,.]+)"             # Grupo 7: Importe
    r"\s*$"                  # Fin de línea
)

# Patrón alternativo: sin números finales (línea cortada o formato reducido)
PATRON_LINEA_PRODUCTO_SIMPLE = re.compile(
    r"^\s*"
    r"(\d+\.\d{2})"          # Grupo 1: Cantidad
    r"\s*"                   # Espacio opcional
    r"(\S{3,})"              # Grupo 2: Clave artículo
    r"\s+"                   # Espacios obligatorios
    r"([A-Z]{2,6})"          # Grupo 3: Línea/familia
    r"\s+"                   # Espacios obligatorios
    r"(.+\S)"                # Grupo 4: Descripción (hasta último no-espacio)
)


def _leer_desde_txt(ruta_txt: str) -> list:
    """
    Lee productos de un TXT exportado desde Aspel SAE (formato columnas fijas).
    Soporta:
    - Espacio opcional entre cantidad y clave (10.00 CPLL04 vs 5.00CBPL10)
    - Claves cortas (9261, 4 chars) y largas (CPLL04-1/8)
    - Limpieza automática de % descuento, costo unitario e importe del final
    - Ignora líneas de clave SAT (27131702  H87) y saltos de página
    """
    datos = []
    with open(ruta_txt, encoding="utf-8", errors="ignore") as f:
        lineas = f.readlines()
        contenido_completo = "".join(lineas)

        for linea_txt in lineas:
            # Intentar primero el patrón completo (con números al final)
            m = PATRON_LINEA_PRODUCTO.match(linea_txt)
            if m:
                cve_art = m.group(2)
                linea = m.group(3)
                descripcion_corta = m.group(4).strip()
                datos.append({
                    "codigo_norm": _normaliza(cve_art),
                    "clave_articulo": cve_art,
                    "linea": linea,
                    "descripcion_corta": descripcion_corta or None,
                })
                continue

            # Intentar patrón simple (sin números al final)
            m2 = PATRON_LINEA_PRODUCTO_SIMPLE.match(linea_txt)
            if m2:
                cve_art = m2.group(2)
                linea = m2.group(3)
                desc_raw = m2.group(4).strip()
                # Limpiar posibles números sueltos al final
                desc_raw = re.sub(r"\s+[\d,.]+\s+[\d,.]+\s*$", "", desc_raw).strip()
                datos.append({
                    "codigo_norm": _normaliza(cve_art),
                    "clave_articulo": cve_art,
                    "linea": linea,
                    "descripcion_corta": desc_raw or None,
                })

    num_proveedor = extraer_numero_proveedor(contenido_completo)
    if num_proveedor:
        for d in datos:
            d["numero_proveedor"] = num_proveedor

    logger.debug("TXT %s: %d productos extraídos, proveedor: %s",
                 os.path.basename(ruta_txt), len(datos), num_proveedor)
    return datos


def _extraer_rfcs_de_texto(texto: str) -> list[str]:
    """Extrae TODOS los RFCs que aparecen en el texto del TXT/PDF de apoyo."""
    if not texto:
        return []
    # Busca todas las ocurrencias de "RFC: XXXXXXX" o "RFC:XXXXXXX"
    return re.findall(r"RFC:\s*([A-ZÑ&]{3,4}\d{6}[A-Z\d]{3})", texto)


def _folio_coincide_con_archivo(ruta_archivo: str, folio: int, rfc_proveedor: str | None = None) -> bool:
    """
    Verifica si un archivo TXT/PDF de apoyo corresponde al XML.
    Estrategia en tres pasos:
    1. RFC del proveedor: lee el archivo y compara el RFC del emisor del XML
       con el que aparece en el TXT/PDF. Es la más robusta.
    2. Número COMPRA: busca 'COMPRA  XXXXX' en el encabezado — match por contención.
    3. Fallback: busca el folio en los dígitos del nombre del archivo.
    """
    folio_str = str(folio)

    try:
        ext = os.path.splitext(ruta_archivo)[1].lower()
        
        if ext == ".txt":
            with open(ruta_archivo, encoding="utf-8", errors="ignore") as f:
                contenido = f.read()
            
            # Paso 1: Match por RFC del proveedor
            if rfc_proveedor:
                rfcs_en_archivo = _extraer_rfcs_de_texto(contenido)
                if rfcs_en_archivo:
                    if rfc_proveedor in rfcs_en_archivo:
                        logger.debug("Match por RFC proveedor: %s en %s", rfc_proveedor, os.path.basename(ruta_archivo))
                        return True
                    else:
                        # Ningún RFC coincide -> definitivamente no es este archivo
                        return False
            
            # Paso 2: Match por número COMPRA
            num_compra = extraer_numero_compra(contenido)
            if num_compra:
                digitos_compra = "".join(c for c in num_compra if c.isdigit())
                if folio_str in digitos_compra or digitos_compra in folio_str:
                    logger.debug("Match por encabezado COMPRA: %s <-> folio %s", num_compra, folio_str)
                    return True
                    
        elif ext == ".pdf":
            with pdfplumber.open(ruta_archivo) as pdf:
                if pdf.pages:
                    texto_pagina1 = pdf.pages[0].extract_text() or ""
                    
                    # Paso 1: Match por RFC
                    if rfc_proveedor:
                        rfcs_en_archivo = _extraer_rfcs_de_texto(texto_pagina1)
                        if rfcs_en_archivo:
                            if rfc_proveedor in rfcs_en_archivo:
                                return True
                            else:
                                return False
                    
                    # Paso 2: Match por COMPRA
                    num_compra = extraer_numero_compra(texto_pagina1)
                    if num_compra:
                        digitos_compra = "".join(c for c in num_compra if c.isdigit())
                        if folio_str in digitos_compra or digitos_compra in folio_str:
                            return True
    except Exception:
        logger.debug("Error leyendo archivo %s, usando fallback por nombre", ruta_archivo)

    # Paso 3: Fallback por nombre de archivo (contención bidireccional)
    nombre = os.path.basename(ruta_archivo)
    digitos_nombre = "".join(c for c in os.path.splitext(nombre)[0] if c.isdigit())
    if not digitos_nombre:
        return False

    return folio_str in digitos_nombre or digitos_nombre in folio_str


def obtener_apoyo_por_folio(carpeta: str, year: str, folio: int, rfc_proveedor: str | None = None) -> list:
    """
    Busca en carpeta un pdf o txt que corresponda al XML usando:
    1. RFC del proveedor (más confiable)
    2. Número COMPRA del encabezado
    3. Nombre del archivo
    Devuelve la lista ordenada de productos. Prioriza PDF sobre TXT si ambos existen.
    """
    candidatos = []
    for nombre in os.listdir(carpeta):
        ext = os.path.splitext(nombre)[1].lower()
        if ext not in (".pdf", ".txt"):
            continue
        ruta_completa = os.path.join(carpeta, nombre)
        if _folio_coincide_con_archivo(ruta_completa, folio, rfc_proveedor):
            candidatos.append(ruta_completa)
    candidatos.sort(key=lambda p: 0 if p.lower().endswith(".pdf") else 1)

    for ruta in candidatos:
        datos = _leer_desde_pdf(ruta) if ruta.lower().endswith(".pdf") else _leer_desde_txt(ruta)
        if datos:
            return datos
    return []


def buscar_dato(apoyo: list, codigo_concepto: str) -> dict | None:
    """Empareja el código del concepto XML contra la lista de apoyo, por código."""
    for dato in apoyo:
        if _coinciden(codigo_concepto, dato["codigo_norm"]):
            return dato
    return None


# Mantener es_apoyo_de_folio como wrapper para sincronizador.py
def es_apoyo_de_folio(nombre_archivo: str, year: str, folio: int) -> bool:
    """
    Verifica si el nombre de archivo (PDF/TXT) corresponde al folio del XML.
    Compara usando contención bidireccional los dígitos del nombre vs el folio.
    """
    nombre_sin_ext = os.path.splitext(nombre_archivo)[0]
    digitos_nombre = "".join(c for c in nombre_sin_ext if c.isdigit())
    if not digitos_nombre:
        return False
    folio_str = str(folio)
    return folio_str in digitos_nombre or digitos_nombre in folio_str


__all__ = ["obtener_apoyo_por_folio", "buscar_dato", "extraer_numero_proveedor", "es_apoyo_de_folio"]
