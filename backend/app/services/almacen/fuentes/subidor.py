"""Agrupa y sube documentos de facturas a Google Drive."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

from app.core.config import settings
from app.services.almacen.fuentes.google_drive_client import (
    buscar_o_crear_carpeta,
    crear_cliente_drive,
    listar_archivos_carpeta,
    subir_archivo,
)


@dataclass(frozen=True)
class GrupoCarga:
    """Una factura y sus documentos de apoyo."""

    xml: Path
    apoyo: tuple[Path, ...]


def _clave_folio(nombre: str) -> tuple[str, int] | None:
    coincidencia = re.search(r"(\d{6,})", nombre)
    if not coincidencia:
        return None
    digitos = coincidencia.group(1)
    return digitos[:4], int(digitos[4:])


def agrupar_documentos(rutas: Iterable[Path]) -> list[GrupoCarga]:
    """Agrupa XML con PDF/TXT por año y folio, tolerando distinto padding."""
    archivos = [Path(ruta) for ruta in rutas]
    xmls = [ruta for ruta in archivos if ruta.suffix.lower() == ".xml"]
    apoyos = [ruta for ruta in archivos if ruta.suffix.lower() in {".pdf", ".txt"}]
    grupos: list[GrupoCarga] = []
    usados: set[Path] = set()

    for xml in xmls:
        clave = _clave_folio(xml.name)
        asociados = tuple(
            apoyo
            for apoyo in apoyos
            if apoyo not in usados and _clave_folio(apoyo.name) == clave
        )
        usados.update(asociados)
        grupos.append(GrupoCarga(xml=xml, apoyo=asociados))

    if len(grupos) == 1:
        restantes = tuple(apoyo for apoyo in apoyos if apoyo not in usados)
        grupos[0] = GrupoCarga(xml=grupos[0].xml, apoyo=grupos[0].apoyo + restantes)
    return grupos


def _nombre_carpeta(xml: Path) -> str:
    """Obtiene fecha CFDI para nombrar carpeta; usa fecha actual como fallback."""
    try:
        raiz = ET.parse(xml).getroot()
        fecha = raiz.attrib.get("Fecha", "")
        fecha = datetime.fromisoformat(fecha.replace("Z", "+00:00"))
    except (ET.ParseError, OSError, TypeError, ValueError):
        fecha = datetime.now()
    return fecha.strftime("%d-%m-%Y")


def subir_documentos_drive(rutas: Iterable[Path]) -> dict[str, int]:
    """Crea carpetas por factura y sube solo archivos no existentes."""
    if not settings.google_drive_folder_id:
        raise RuntimeError("Falta GOOGLE_DRIVE_FOLDER_ID")

    grupos = agrupar_documentos(rutas)
    if not grupos:
        raise ValueError("Se requiere al menos un XML")

    cliente = crear_cliente_drive()
    carpetas = 0
    subidos = 0
    omitidos = 0
    for grupo in grupos:
        carpeta_id = buscar_o_crear_carpeta(
            cliente,
            _nombre_carpeta(grupo.xml),
            settings.google_drive_folder_id,
        )
        carpetas += 1
        existentes = {
            archivo["name"]
            for archivo in listar_archivos_carpeta(cliente, carpeta_id)
        }
        for ruta in (grupo.xml, *grupo.apoyo):
            if ruta.name in existentes:
                omitidos += 1
                continue
            subir_archivo(cliente, ruta, carpeta_id)
            subidos += 1

    return {
        "facturas": len(grupos),
        "carpetas": carpetas,
        "subidos": subidos,
        "omitidos": omitidos,
    }


__all__ = ["GrupoCarga", "agrupar_documentos", "subir_documentos_drive"]
