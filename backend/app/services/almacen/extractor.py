"""
Extractor de conceptos desde CFDI 4.0 (XML del proveedor).
"""

from __future__ import annotations

import os
import re
import xml.etree.ElementTree as ET
from pathlib import Path


NS = {"cfdi": "http://www.sat.gob.mx/cfd/4"}

# Carpeta donde Compras deja xml + txt/pdf (mismo nombre base, distinta extensiÃ³n)
CARPETA_DATOS = Path(
    os.getenv(
        "ALMACEN_CARPETA_DATOS",
        Path(__file__).resolve().parents[3] / "datos" / "almacen",
    )
)

PATRON_CON_CORCHETE = re.compile(r"^\[[^\]]+\]\s+(\S+)")
PATRON_PRIMER_TOKEN = re.compile(r"^(\S+)")


def _codigo_desde_descripcion(descripcion: str) -> str | None:
    """
    NoIdentificacion es opcional en el CFDI. Si falta, el cÃ³digo de producto
    suele venir al inicio de Descripcion, con dos formatos vistos hasta ahora:
      Makronix:  "[011040P005] 25KL4P05000 Indicador..." -> nos interesa el 2do token
      Universal: "UQ62-DOT-06 UniÃ³n RÃ¡pida..."            -> nos interesa el 1er token
    """
    if not descripcion:
        return None
    m = PATRON_CON_CORCHETE.match(descripcion)
    if m:
        return m.group(1)
    m = PATRON_PRIMER_TOKEN.match(descripcion)
    return m.group(1) if m else None


def leer_meta(ruta_xml: str | Path) -> dict:
    """Folio y aÃ±o del comprobante, para emparejar con el pdf/txt de apoyo por folio real."""
    root = ET.parse(ruta_xml).getroot()
    folio = root.get("Folio")
    fecha = root.get("Fecha") or ""
    year = fecha[:4] if fecha else None
    return {"folio": int(folio) if folio else None, "year": year}


def extraer_conceptos(ruta_xml: str | Path) -> list[dict]:
    """
    Lee un CFDI 4.0 y devuelve una lista de dicts, uno por concepto/producto.
    """
    tree = ET.parse(ruta_xml)
    root = tree.getroot()

    emisor = root.find("cfdi:Emisor", NS)
    proveedor_nombre = emisor.get("Nombre") if emisor is not None else None
    proveedor_rfc = emisor.get("Rfc") if emisor is not None else None
    fecha_factura = root.get("Fecha")

    conceptos_nodo = root.find("cfdi:Conceptos", NS)
    if conceptos_nodo is None:
        return []

    filas = []
    for c in conceptos_nodo.findall("cfdi:Concepto", NS):
        descripcion = c.get("Descripcion")
        codigo_desc = _codigo_desde_descripcion(descripcion)
        no_identificacion = c.get("NoIdentificacion") or codigo_desc

        filas.append({
            "no_identificacion": no_identificacion,
            "codigo_secundario": codigo_desc,  # para emparejar con Cve.Art. del pdf/txt de apoyo
            "descripcion": descripcion,
            "clave_prod_serv": c.get("ClaveProdServ"),
            "clave_unidad": c.get("ClaveUnidad"),
            "cantidad": float(c.get("Cantidad", 0)),
            "valor_unitario": float(c.get("ValorUnitario", 0)),
            "proveedor_nombre": proveedor_nombre,
            "proveedor_rfc": proveedor_rfc,
            "fecha_compra": fecha_factura,
        })
    return filas


__all__ = ["CARPETA_DATOS", "extraer_conceptos", "leer_meta"]
