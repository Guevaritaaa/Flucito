"""Paquete de herramientas ortogonales orientadas a recursos para el agente Flucito."""

from __future__ import annotations

from app.agents.tools.almacen_tools import (
    actualizar_precios_reportes_generados,
    consultar_almacen,
    generar_entradas_almacen,
)
from app.agents.tools.drive_tools import (
    consultar_drive,
    gestionar_archivos_drive,
    preparar_entorno_pruebas,
)
from app.services.almacen.excel import CARPETA_DATOS

HERRAMIENTAS = [
    consultar_drive,
    gestionar_archivos_drive,
    consultar_almacen,
    generar_entradas_almacen,
    actualizar_precios_reportes_generados,
    preparar_entorno_pruebas,
]

__all__ = [
    "CARPETA_DATOS",
    "HERRAMIENTAS",
    "consultar_drive",
    "gestionar_archivos_drive",
    "consultar_almacen",
    "generar_entradas_almacen",
    "actualizar_precios_reportes_generados",
    "preparar_entorno_pruebas",
]
