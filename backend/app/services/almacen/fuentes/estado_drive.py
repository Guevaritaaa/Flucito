"""Estado local para sincronización incremental de Google Drive."""

from __future__ import annotations

import json
from pathlib import Path

from app.services.almacen.fuentes.google_drive import CarpetaFactura


NOMBRE_ESTADO = "ESTADO_DRIVE_ALMACEN.json"


def cargar_estado(ruta: str | Path) -> dict[str, dict[str, str]]:
    """Carga fileId y modifiedTime procesados; estado vacío si no existe."""
    archivo = Path(ruta)
    if not archivo.is_file():
        return {"archivos": {}}
    try:
        datos = json.loads(archivo.read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError):
        return {"archivos": {}}
    return {"archivos": datos.get("archivos", {})}


def guardar_estado(ruta: str | Path, estado: dict[str, dict[str, str]]) -> None:
    """Persiste estado solo después de completar sincronización."""
    archivo = Path(ruta)
    archivo.parent.mkdir(parents=True, exist_ok=True)
    archivo.write_text(
        json.dumps(estado, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def carpetas_con_novedades(
    carpetas: list[CarpetaFactura],
    estado: dict[str, dict[str, str]],
) -> list[CarpetaFactura]:
    """Devuelve carpetas con archivo nuevo o con modifiedTime actualizado."""
    procesados = estado.setdefault("archivos", {})
    resultado = []
    for carpeta in carpetas:
        tiene_novedad = any(
            procesados.get(archivo.id) != (archivo.modificado or "")
            for archivo in carpeta.archivos
        )
        if tiene_novedad:
            resultado.append(carpeta)
    return resultado


def marcar_procesadas(
    carpetas: list[CarpetaFactura],
    estado: dict[str, dict[str, str]],
) -> None:
    """Marca documentos solo de carpetas procesadas exitosamente."""
    procesados = estado.setdefault("archivos", {})
    for carpeta in carpetas:
        for archivo in carpeta.archivos:
            procesados[archivo.id] = archivo.modificado or ""


__all__ = [
    "NOMBRE_ESTADO",
    "cargar_estado",
    "carpetas_con_novedades",
    "guardar_estado",
    "marcar_procesadas",
]
