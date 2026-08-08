"""Modelos y agrupaciÃ³n de documentos provenientes de Google Drive."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


EXTENSIONES_DOCUMENTO = {".xml", ".pdf", ".txt"}
MIME_CARPETA = "application/vnd.google-apps.folder"


@dataclass(frozen=True)
class DriveArchivo:
    """Metadatos mÃ­nimos de un archivo listado por Drive."""

    id: str
    nombre: str
    mime_type: str
    modificado: str | None
    carpeta_id: str

    @property
    def extension(self) -> str:
        return Path(self.nombre).suffix.lower()


@dataclass(frozen=True)
class CarpetaFactura:
    """Unidad de trabajo: carpeta con XML y documentos de apoyo."""

    id: str
    nombre: str
    archivos: tuple[DriveArchivo, ...]

    @property
    def xml(self) -> tuple[DriveArchivo, ...]:
        return tuple(archivo for archivo in self.archivos if archivo.extension == ".xml")

    @property
    def apoyo(self) -> tuple[DriveArchivo, ...]:
        return tuple(
            archivo
            for archivo in self.archivos
            if archivo.extension in {".pdf", ".txt"}
        )


def agrupar_por_carpeta(
    carpetas: Iterable[dict],
    archivos: Iterable[dict],
) -> list[CarpetaFactura]:
    """Agrupa archivos hijos por subcarpeta, ignorando tipos no soportados."""
    nombres = {
        carpeta["id"]: carpeta.get("name", carpeta["id"])
        for carpeta in carpetas
        if carpeta.get("mimeType") == MIME_CARPETA
    }
    agrupados: dict[str, list[DriveArchivo]] = {carpeta_id: [] for carpeta_id in nombres}

    for archivo in archivos:
        extension = Path(archivo.get("name", "")).suffix.lower()
        if extension not in EXTENSIONES_DOCUMENTO:
            continue
        padres = archivo.get("parents", [])
        carpeta_id = next((padre for padre in padres if padre in nombres), None)
        if carpeta_id is None:
            continue
        agrupados[carpeta_id].append(
            DriveArchivo(
                id=archivo["id"],
                nombre=archivo["name"],
                mime_type=archivo.get("mimeType", ""),
                modificado=archivo.get("modifiedTime"),
                carpeta_id=carpeta_id,
            )
        )

    return [
        CarpetaFactura(
            id=carpeta_id,
            nombre=nombres[carpeta_id],
            archivos=tuple(archivos_de_carpeta),
        )
        for carpeta_id, archivos_de_carpeta in agrupados.items()
        if any(archivo.extension == ".xml" for archivo in archivos_de_carpeta)
    ]


__all__ = [
    "CarpetaFactura",
    "DriveArchivo",
    "agrupar_por_carpeta",
]
