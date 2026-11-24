"""Explicaciones reproducibles basadas en las fuentes efectivamente consultadas."""
from __future__ import annotations


def explicar_producto(clave: str, meta: dict) -> str:
    fuentes = meta.get("fuentes", {})
    if not fuentes:
        return ""
    partes = [f"Producto {clave}."]
    apoyo = fuentes.get("apoyo", {})
    estado = apoyo.get("estado")
    tipo = apoyo.get("tipo") or "TXT/PDF"
    codigo = apoyo.get("clave")
    xml = fuentes.get("xml", {}).get("clave")
    if codigo:
        if xml and codigo != clave and clave.startswith(codigo):
            partes.append(f"La clave del artículo está incompleta en el {tipo}: {codigo}. El XML aporta {xml}.")
        else:
            partes.append(f"El {tipo} aporta la clave {codigo}. El XML aporta {xml or 'un código vacío'}.")
    else:
        partes.append(f"El XML aporta la clave {xml or 'vacía'}.")
    if estado == "LECTURA_FALLIDA":
        partes.append("No se pudo leer el documento de apoyo; no se puede afirmar que su columna de línea esté vacía.")
    elif estado == "SIN_PARTIDA":
        partes.append("El apoyo se leyó, pero no fue posible emparejar esta partida; no se comprobó su columna de línea.")
    elif estado == "AUSENTE":
        partes.append("No se encontró un documento de apoyo correspondiente a esta factura.")
    elif apoyo.get("linea_original"):
        partes.append(f"La línea en el {tipo} es {apoyo['linea_original']}.")
    elif estado == "LEIDO":
        partes.append(f"La columna de línea de esta partida está vacía en el {tipo}.")
    sae = fuentes.get("catalogo", {})
    if sae.get("clave"):
        partes.append(f"El catálogo del SAE confirmó la clave {sae['clave']} ({sae.get('coincidencia', 'coincidencia registrada')}).")
        partes.append(f"Su línea en el catálogo del SAE es {sae['linea']}." if sae.get("linea") else
                      "Ese artículo tampoco tiene línea en el catálogo del SAE.")
    else:
        partes.append("No se encontró una coincidencia del artículo en el catálogo del SAE.")
    origen = meta.get("origen_linea")
    if origen == "SIN_LINEA":
        partes.append("La línea y los cinco precios de venta quedan pendientes; se conserva el costo de compra extraído.")
    elif origen in {"ASESOR_REFERENCIA", "ASESOR_EXCEL"}:
        partes.append(f"El asesor confirmó la línea {meta.get('linea_confirmada')}. "
                      f"Factor: {meta.get('factor') or 'pendiente de elegir'}.")
        ref = meta.get("referencia_linea")
        if ref:
            partes.append(f"Referencia utilizada: {ref['cve_art']} — {ref.get('descr', '')}, línea {ref['linea']}.")
    else:
        nombres = {"INVE02": "catálogo del SAE", "TXT_APOYO": tipo,
                   "APOYO_LINEA_UNICA": "otras partidas del mismo apoyo",
                   "VARIANTE_MISMA_FACTURA": "otra medida de la misma familia en la factura",
                   "HISTORIAL_UNICA": "historial de compras del proveedor",
                   "HISTORIAL_KEYWORD": "historial de compras y descripción",
                   "VARIANTE_INVE02": "familia de artículos en el catálogo del SAE"}
        partes.append(f"La línea utilizada procede de {nombres.get(origen, origen or 'fuente no registrada')}.")
    return " ".join(partes)
