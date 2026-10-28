"""Herramientas del agente para consultar, auditar y gestionar archivos y carpetas en Google Drive."""

from __future__ import annotations

import json
import logging
from typing import Literal

from langchain_core.tools import tool

from app.agents.tools.schemas import (
    ConsultarDriveInput,
    GestionarArchivosDriveInput,
)
from app.services.almacen.fuentes.google_drive_client import (
    buscar_reportes_historicos,
    normalizar_fecha_reporte,
)
from app.services.almacen.fuentes.navegador_drive import (
    auditar_facturas_drive,
    crear_carpeta_por_ruta,
    eliminar_elemento_por_ruta,
    explorar_estructura_drive,
    mover_elemento_por_ruta,
)
from app.services.almacen.fuentes.organizador import (
    construir_advertencia_ubicacion,
    mover_carpetas_con_reportes_drive,
    ordenar_todo_drive,
    reubicar_carpetas_mal_ubicadas,
)

logger = logging.getLogger(__name__)


@tool(args_schema=ConsultarDriveInput)
def consultar_drive(
    modo_consulta: Literal[
        "explorar_estructura",
        "auditar_facturas",
        "buscar_reportes_excel",
    ],
    ubicacion: Literal[
        "todas",
        "entradas_al_inventario",
        "documentos_entrada",
        "raiz",
    ] = "todas",
    carpeta_o_fecha: str | None = None,
    filtro_auditoria: Literal[
        "todos",
        "incompletas",
        "sin_xml",
        "sin_apoyo",
        "sin_reporte_excel",
        "completas",
    ] = "todos",
    proveedor: str | None = None,
    incluir_archivos: bool = True,
) -> str:
    """Inspecciona Google Drive en modo solo lectura: explora carpetas/archivos, audita facturas incompletas o busca reportes Excel históricos."""
    try:
        if modo_consulta == "explorar_estructura":
            resultado = explorar_estructura_drive(
                ubicacion=ubicacion,
                carpeta_o_fecha=carpeta_o_fecha,
                incluir_archivos=incluir_archivos,
            )
            return json.dumps(resultado, ensure_ascii=False)

        if modo_consulta == "auditar_facturas":
            resultado = auditar_facturas_drive(
                ubicacion=ubicacion,
                carpeta_o_fecha=carpeta_o_fecha,
                filtro_auditoria=filtro_auditoria,
            )
            return json.dumps(resultado, ensure_ascii=False)

        if modo_consulta == "buscar_reportes_excel":
            fecha_normalizada = (
                normalizar_fecha_reporte(carpeta_o_fecha)
                if carpeta_o_fecha and carpeta_o_fecha.strip()
                else None
            )
            reportes = buscar_reportes_historicos(
                fecha=carpeta_o_fecha,
                proveedor=proveedor,
            )
            return json.dumps(
                {
                    "ok": True,
                    "tipo": "busqueda_historica",
                    "fecha": fecha_normalizada,
                    "proveedor": proveedor,
                    "total_reportes": len(reportes),
                    "reportes": reportes,
                },
                ensure_ascii=False,
            )

        return json.dumps(
            {
                "ok": False,
                "error": f"Modo de consulta no soportado: {modo_consulta}",
            },
            ensure_ascii=False,
        )
    except ValueError as error:
        tipo_error = (
            "busqueda_historica"
            if modo_consulta == "buscar_reportes_excel"
            else modo_consulta
        )
        return json.dumps(
            {"ok": False, "tipo": tipo_error, "error": str(error)},
            ensure_ascii=False,
        )
    except Exception as error:
        logger.exception("Error al ejecutar consultar_drive (%s): %s", modo_consulta, error)
        tipo_error = (
            "busqueda_historica"
            if modo_consulta == "buscar_reportes_excel"
            else modo_consulta
        )
        return json.dumps(
            {"ok": False, "tipo": tipo_error, "error": str(error)},
            ensure_ascii=False,
        )


@tool(args_schema=GestionarArchivosDriveInput)
def gestionar_archivos_drive(
    accion: Literal[
        "organizar_todo",
        "archivar_carpetas_procesadas",
        "reubicar_mal_ubicadas",
        "mover_elemento",
        "crear_carpeta",
        "eliminar_elemento",
    ],
    ruta_origen: str | None = None,
    ruta_destino: str | None = None,
    confirmar_eliminar_con_contenido: bool = False,
) -> str:
    """Ejecuta acciones de organización masiva o gestión puntual (crear, mover o eliminar carpetas y archivos) en Google Drive."""
    try:
        if accion == "organizar_todo":
            resultado = ordenar_todo_drive()
            return json.dumps(resultado, ensure_ascii=False)

        if accion == "archivar_carpetas_procesadas":
            resultado = mover_carpetas_con_reportes_drive()
            return json.dumps(resultado, ensure_ascii=False)

        if accion == "reubicar_mal_ubicadas":
            reubicacion = reubicar_carpetas_mal_ubicadas()
            carpetas_reubicadas = reubicacion.get("carpetas_reubicadas", [])
            respuesta = {
                "ok": True,
                "tipo": "reubicar_mal_ubicadas",
                **reubicacion,
                "mensaje": (
                    construir_advertencia_ubicacion(carpetas_reubicadas)
                    if carpetas_reubicadas
                    else "No se encontraron carpetas mal ubicadas en DOCUMENTOS ENTRADA."
                ),
            }
            return json.dumps(respuesta, ensure_ascii=False)

        if accion == "mover_elemento":
            resultado = mover_elemento_por_ruta(
                ruta_origen=ruta_origen or "",
                ruta_destino=ruta_destino or "",
            )
            return json.dumps(resultado, ensure_ascii=False)

        if accion == "crear_carpeta":
            ruta_nueva = ruta_destino or ruta_origen or ""
            resultado = crear_carpeta_por_ruta(ruta_nueva_carpeta=ruta_nueva)
            return json.dumps(resultado, ensure_ascii=False)

        if accion == "eliminar_elemento":
            objetivo = ruta_origen or ruta_destino or ""
            resultado = eliminar_elemento_por_ruta(
                ruta_objetivo=objetivo,
                confirmar_eliminar_con_contenido=confirmar_eliminar_con_contenido,
            )
            return json.dumps(resultado, ensure_ascii=False)

        return json.dumps(
            {"ok": False, "accion": accion, "error": f"Acción no soportada: {accion}"},
            ensure_ascii=False,
        )
    except Exception as error:
        logger.exception("Error en gestionar_archivos_drive (%s): %s", accion, error)
        return json.dumps(
            {"ok": False, "tipo": accion, "error": str(error)},
            ensure_ascii=False,
        )


@tool
def preparar_entorno_pruebas() -> str:
    """Restaura el entorno de pruebas en Google Drive borrando reportes generados y regresando archivos a ENTRADAS AL INVENTARIO."""
    try:
        from app.services.almacen.fuentes.limpieza import restaurar_entorno_pruebas

        resultado = restaurar_entorno_pruebas()
        return json.dumps(resultado, ensure_ascii=False)
    except Exception as error:
        logger.exception("Error al restaurar entorno de pruebas: %s", error)
        return json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False)


__all__ = [
    "consultar_drive",
    "gestionar_archivos_drive",
    "preparar_entorno_pruebas",
]
