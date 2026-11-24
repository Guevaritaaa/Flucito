"""Sugerencias de referencia: nunca se aplican sin una decisión por producto."""
from __future__ import annotations
import os
import re

from app.services.almacen.catalogo_sae import cargar_catalogo_sae


def normalizar_linea(valor):
    """INVE02.LIN_PROD y CLIN02.CVE_LIN admiten cinco caracteres en SAE 9."""
    codigo = str(valor or "").strip().upper()
    if not re.fullmatch(r"[A-Z0-9][A-Z0-9_-]{0,4}", codigo):
        raise ValueError("La línea debe tener de 1 a 5 caracteres: letras, números, guion o guion bajo; sin espacios.")
    return codigo


def _familia(codigo):
    codigo = str(codigo or "").strip().upper()
    inicio = re.match(r"([A-Z]+(?:-[A-Z]+)*-?)(?=\d)", codigo)
    # No compactar signos ni fracciones: 1/4 y 14 son medidas distintas.
    medidas = tuple(re.findall(r"\d+(?:[./]\d+)?", codigo))
    return (inicio[1], medidas) if inicio and medidas else None


def sugerir_lineas(clave, clave_sat, unidad_sat):
    familia = _familia(clave)
    if not familia or not clave_sat or not unidad_sat:
        return []
    referencias = []
    for art in cargar_catalogo_sae().get("articulos_exactos", {}).values():
        if (not art.get("linea") or art.get("cve_art") == clave or
            str(art.get("cve_sat") or "").strip() != str(clave_sat).strip() or
            str(art.get("cve_unidad") or "").strip().upper() != str(unidad_sat).strip().upper() or
            _familia(art.get("cve_art")) != familia):
            continue
        referencias.append({k: art.get(k, "") for k in ("cve_art", "descr", "linea", "cve_sat", "cve_unidad")})
    referencias.sort(key=lambda a: (-len(os.path.commonprefix([str(clave), a["cve_art"]])), a["cve_art"]))
    grupos = {}
    for ref in referencias[:3]:
        grupos.setdefault(ref["linea"], []).append(ref)
    return [{"linea": linea, "referencias": refs} for linea, refs in grupos.items()]


def aplicar_decision(clave, sat, unidad, decisiones):
    decision = (decisiones or {}).get(str(clave))
    if not decision:
        return None
    if decision.get("manual") is True:
        return {"manual": True}
    for grupo in sugerir_lineas(clave, sat, unidad):
        if grupo["linea"] == decision.get("linea"):
            for ref in grupo["referencias"]:
                if ref["cve_art"] == decision.get("referencia") and decision.get("confirmada") is True:
                    return {"linea": normalizar_linea(grupo["linea"]), "referencia": ref}
    raise ValueError(f"La referencia o confirmación de línea para {clave} ya no es válida. Revisa las sugerencias.")
