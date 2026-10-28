"""Herramientas del agente para consultar la base de almacén, generar reportes y actualizar precios."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Literal

import pandas as pd
from langchain_core.tools import tool

from app.agents.tools.schemas import (
    ActualizarPreciosReportesInput,
    ConsultarAlmacenInput,
    GenerarEntradasAlmacenInput,
)
from app.core.config import settings
from app.services.almacen.excel import (
    CARPETA_DATOS as _CARPETA_DATOS_DEFAULT,
    NOMBRE_ARCHIVO_RESUMEN,
    actualizar_precios_reporte_existente,
    procesar_carpeta,
)
from app.services.almacen.factores import (
    CATALOGO_FACTORES,
    CATALOGO_LINEAS_BASE,
    cargar_factores_personalizados,
    formatear_menu_factores,
    guardar_factor_personalizado,
)
from app.services.almacen.fuentes.organizador import construir_advertencia_ubicacion
from app.services.almacen.fuentes.sincronizador import (
    actualizar_precios_reportes_drive,
    construir_pregunta_interactiva,
    inspeccionar_pendientes_carpeta,
    sincronizar_drive,
)

logger = logging.getLogger(__name__)


def _obtener_carpeta_datos() -> Path:
    """Obtiene la carpeta de datos actual, respetando monkeypatches sobre app.agents.tools.CARPETA_DATOS."""
    try:
        from app.agents import tools as paquete_tools

        return Path(getattr(paquete_tools, "CARPETA_DATOS", _CARPETA_DATOS_DEFAULT))
    except Exception:
        return Path(_CARPETA_DATOS_DEFAULT)


def _normalizar_decisiones_rollos(
    cambiar_xro_a_mtr: bool | None,
    dividir_precio_entre_metros: bool | None,
    decisiones_rollos: dict[str, dict[str, object]] | None,
) -> dict[str, dict[str, object]] | None:
    """Combina banderas globales de rollo/metros con decisiones por clave de artículo."""
    combinadas: dict[str, dict[str, object]] = {
        str(k): dict(v)
        for k, v in (decisiones_rollos or {}).items()
        if isinstance(v, dict)
    }
    if cambiar_xro_a_mtr is not None or dividir_precio_entre_metros is not None:
        comodin = dict(combinadas.get("*", {}))
        if cambiar_xro_a_mtr is not None:
            comodin["cambiar_a_mtr"] = bool(cambiar_xro_a_mtr)
        if dividir_precio_entre_metros is not None:
            comodin["dividir_entre_metros"] = bool(dividir_precio_entre_metros)
        combinadas["*"] = comodin
    return combinadas or None


@tool(args_schema=ConsultarAlmacenInput)
def consultar_almacen(
    tipo_consulta: Literal[
        "resumen_general",
        "buscar_entradas",
        "catalogo_factores",
    ] = "resumen_general",
    proveedor: str | None = None,
    linea: str | None = None,
    producto_o_clave: str | None = None,
    folio_factura: str | None = None,
    fecha: str | None = None,
    limite: int = 25,
) -> str:
    """Consulta en modo lectura el resumen general del almacén, busca entradas en la base acumulada o consulta el catálogo de factores de utilidad."""
    carpeta_datos = _obtener_carpeta_datos()
    try:
        if tipo_consulta == "catalogo_factores":
            personalizados = cargar_factores_personalizados()
            if linea and linea.strip():
                codigo_buscado = linea.strip().upper()
                info_base = CATALOGO_LINEAS_BASE.get(codigo_buscado)
                info_custom = personalizados.get(codigo_buscado)
                factor_asignado = (
                    (info_custom or {}).get("factor")
                    if info_custom
                    else (info_base or {}).get("factor")
                )
                formulas = (
                    CATALOGO_FACTORES.get(str(factor_asignado))
                    if factor_asignado
                    else None
                )
                return json.dumps(
                    {
                        "ok": True,
                        "tipo": "consultar_almacen",
                        "tipo_consulta": "catalogo_factores",
                        "linea_consultada": codigo_buscado,
                        "registrada_en_base": info_base is not None,
                        "descripcion_linea": (info_base or {}).get("descripcion"),
                        "factor_asignado": factor_asignado,
                        "es_factor_personalizado": info_custom is not None,
                        "formulas_precio": formulas,
                    },
                    ensure_ascii=False,
                )

            return json.dumps(
                {
                    "ok": True,
                    "tipo": "consultar_almacen",
                    "tipo_consulta": "catalogo_factores",
                    "factores_disponibles": CATALOGO_FACTORES,
                    "menu_factores": formatear_menu_factores(),
                    "factores_personalizados": personalizados,
                    "total_lineas_catalogo_base": len(CATALOGO_LINEAS_BASE),
                },
                ensure_ascii=False,
            )

        ruta_resumen = carpeta_datos / NOMBRE_ARCHIVO_RESUMEN
        ruta_base_excel = carpeta_datos / "BASE_ENTRADAS_ALMACEN.xlsx"

        if tipo_consulta == "resumen_general":
            if ruta_resumen.is_file():
                resumen = json.loads(ruta_resumen.read_text(encoding="utf-8"))
                return json.dumps(
                    {
                        "ok": True,
                        "tipo": "consultar_almacen",
                        "tipo_consulta": "resumen_general",
                        "tiene_datos": True,
                        "resumen": resumen,
                    },
                    ensure_ascii=False,
                )
            return json.dumps(
                {
                    "ok": True,
                    "tipo": "consultar_almacen",
                    "tipo_consulta": "resumen_general",
                    "tiene_datos": False,
                    "mensaje": "Aún no existe un resumen acumulado de entradas en el almacén local.",
                },
                ensure_ascii=False,
            )

        if tipo_consulta == "buscar_entradas":
            if not ruta_base_excel.is_file():
                return json.dumps(
                    {
                        "ok": True,
                        "tipo": "consultar_almacen",
                        "tipo_consulta": "buscar_entradas",
                        "tiene_datos": False,
                        "total_coincidencias": 0,
                        "entradas": [],
                        "mensaje": "No se encontró el archivo BASE_ENTRADAS_ALMACEN.xlsx en el almacén local.",
                    },
                    ensure_ascii=False,
                )

            tabla = pd.read_excel(ruta_base_excel)
            mascara = pd.Series([True] * len(tabla), index=tabla.index)

            if proveedor and proveedor.strip() and "PROVEEDOR" in tabla.columns:
                filtro_prov = proveedor.strip().casefold()
                mascara &= (
                    tabla["PROVEEDOR"]
                    .fillna("")
                    .astype(str)
                    .str.casefold()
                    .str.contains(filtro_prov, regex=False)
                )

            if linea and linea.strip() and "Línea" in tabla.columns:
                filtro_lin = linea.strip().casefold()
                mascara &= (
                    tabla["Línea"]
                    .fillna("")
                    .astype(str)
                    .str.casefold()
                    .str.contains(filtro_lin, regex=False)
                )

            if producto_o_clave and producto_o_clave.strip():
                filtro_prod = producto_o_clave.strip().casefold()
                coincide_clave = (
                    tabla["Clave Artículo"]
                    .fillna("")
                    .astype(str)
                    .str.casefold()
                    .str.contains(filtro_prod, regex=False)
                    if "Clave Artículo" in tabla.columns
                    else False
                )
                coincide_desc = (
                    tabla["DESCRIPCION"]
                    .fillna("")
                    .astype(str)
                    .str.casefold()
                    .str.contains(filtro_prod, regex=False)
                    if "DESCRIPCION" in tabla.columns
                    else False
                )
                mascara &= coincide_clave | coincide_desc

            if folio_factura and folio_factura.strip() and "FOLIO" in tabla.columns:
                filtro_folio = folio_factura.strip().casefold()
                mascara &= (
                    tabla["FOLIO"]
                    .fillna("")
                    .astype(str)
                    .str.casefold()
                    .str.contains(filtro_folio, regex=False)
                )

            if fecha and fecha.strip():
                filtro_fecha = fecha.strip().casefold()
                columna_fecha = (
                    "Fecha de última compra"
                    if "Fecha de última compra" in tabla.columns
                    else ("FECHA" if "FECHA" in tabla.columns else None)
                )
                if columna_fecha:
                    mascara &= (
                        tabla[columna_fecha]
                        .fillna("")
                        .astype(str)
                        .str.casefold()
                        .str.contains(filtro_fecha, regex=False)
                    )

            filtrada = tabla[mascara]
            columnas_relevantes = [
                col
                for col in (
                    "Clave Artículo",
                    "DESCRIPCION",
                    "Línea",
                    "Clave unidad",
                    "PROVEEDOR",
                    "PRECIO COMPRA",
                    "PUBLICO",
                    "DISTRIBUIDOR",
                    "MINIMO",
                    "Existencias",
                    "Fecha de última compra",
                    "FECHA",
                    "FOLIO",
                )
                if col in filtrada.columns
            ]
            recorte = filtrada[columnas_relevantes].head(limite).fillna("")
            registros: list[dict[str, Any]] = recorte.to_dict(orient="records")

            return json.dumps(
                {
                    "ok": True,
                    "tipo": "consultar_almacen",
                    "tipo_consulta": "buscar_entradas",
                    "tiene_datos": True,
                    "total_coincidencias": int(len(filtrada)),
                    "mostrando": len(registros),
                    "entradas": registros,
                },
                ensure_ascii=False,
            )

        return json.dumps(
            {"ok": False, "error": f"Tipo de consulta no soportado: {tipo_consulta}"},
            ensure_ascii=False,
        )
    except Exception as error:
        logger.exception("Error en consultar_almacen (%s): %s", tipo_consulta, error)
        return json.dumps(
            {"ok": False, "tipo": "consultar_almacen", "error": str(error)},
            ensure_ascii=False,
        )


@tool(args_schema=GenerarEntradasAlmacenInput)
def generar_entradas_almacen(
    confirmar_solo_xml: bool | None = None,
    factores_elegidos: dict[str, str] | None = None,
    guardar_factores: bool | None = None,
    cambiar_xro_a_mtr: bool | None = None,
    dividir_precio_entre_metros: bool | None = None,
    decisiones_rollos: dict[str, dict[str, object]] | None = None,
) -> str:
    """Sincroniza facturas nuevas desde Google Drive o carpeta local, genera reportes Excel y actualiza la base acumulada."""
    carpeta_datos = _obtener_carpeta_datos()
    usar_drive = bool(
        settings.google_drive_folder_id
        and (
            settings.google_oauth_client_json
            or settings.google_oauth_client_file
            or settings.google_service_account_json
            or settings.google_service_account_file
        )
    )
    logger.info("Tool 'generar_entradas_almacen' invocada. Modo Google Drive: %s", usar_drive)

    decisiones_rollos_norm = _normalizar_decisiones_rollos(
        cambiar_xro_a_mtr,
        dividir_precio_entre_metros,
        decisiones_rollos,
    )

    if usar_drive:
        try:
            sincronizacion = sincronizar_drive(
                interactivo=True,
                confirmar_solo_xml=confirmar_solo_xml,
                factores_elegidos=factores_elegidos,
                guardar_factores=guardar_factores,
                decisiones_rollos=decisiones_rollos_norm,
            )
        except Exception as error:
            logger.exception("Error durante sincronización con Drive: %s", error)
            return json.dumps(
                {"ok": False, "error": str(error)},
                ensure_ascii=False,
            )

        if sincronizacion.get("cancelado_por_usuario"):
            return json.dumps(
                {
                    "ok": True,
                    "reporte_generado": False,
                    "cancelado_por_usuario": True,
                    "mensaje": sincronizacion["mensaje"],
                },
                ensure_ascii=False,
            )

        if sincronizacion.get("requiere_confirmacion"):
            return json.dumps(
                {
                    "ok": True,
                    "reporte_generado": False,
                    **sincronizacion,
                },
                ensure_ascii=False,
            )

        carpetas_reubicadas = sincronizacion.get("carpetas_reubicadas") or []
        if sincronizacion["carpetas"] == 0 or sincronizacion.get("carpetas_nuevas", 0) == 0:
            logger.info("Drive: Sin documentos nuevos o carpetas. Verificando si existe base previa...")
            ruta_resumen = carpeta_datos / NOMBRE_ARCHIVO_RESUMEN
            ruta_base = carpeta_datos / "BASE_ENTRADAS_ALMACEN.xlsx"
            if ruta_base.is_file():
                try:
                    actualizar_precios_reporte_existente(
                        str(ruta_base),
                        carpeta_apoyo=str(carpeta_datos),
                        factores_elegidos=factores_elegidos,
                        actualizar_resumen=True,
                    )
                except Exception as error_precios:
                    logger.warning("No se pudo actualizar precios en base previa: %s", error_precios)
            if ruta_base.is_file() and ruta_resumen.is_file():
                try:
                    resumen = json.loads(ruta_resumen.read_text(encoding="utf-8"))
                    resumen["origen"] = "google_drive"
                    resumen["documentos_nuevos"] = 0
                    respuesta_sin_nuevos: dict = {
                        "ok": True,
                        "reporte_generado": True,
                        "documentos_nuevos": 0,
                        "mensaje": "No hay documentos nuevos en Google Drive. La base acumulada ya está al día.",
                        "resumen": resumen,
                    }
                    if carpetas_reubicadas:
                        respuesta_sin_nuevos["carpetas_reubicadas"] = carpetas_reubicadas
                        respuesta_sin_nuevos["advertencia_ubicacion"] = construir_advertencia_ubicacion(
                            carpetas_reubicadas
                        )
                    return json.dumps(respuesta_sin_nuevos, ensure_ascii=False)
                except (OSError, ValueError):
                    pass

            logger.info("Drive: No hay documentos nuevos ni base previa generada.")
            if sincronizacion["carpetas"] == 0:
                return json.dumps(
                    {
                        "ok": False,
                        "error": "No hay subcarpetas con documentos en Google Drive y no hay base generada.",
                    },
                    ensure_ascii=False,
                )

            return json.dumps(
                {
                    "ok": True,
                    "reporte_generado": False,
                    "documentos_nuevos": 0,
                    "mensaje": "No hay documentos nuevos en Google Drive",
                },
                ensure_ascii=False,
            )

    else:
        sincronizacion = {"origen": "local"}
        carpetas_reubicadas = []

    carpeta = carpeta_datos
    if not usar_drive and not carpeta.is_dir():
        logger.warning("Carpeta local de almacén no encontrada: %s", carpeta)
        return json.dumps(
            {"ok": False, "error": "Carpeta de almacén no encontrada"},
            ensure_ascii=False,
        )

    rutas_xml_locales = (
        [p for p in carpeta.iterdir() if p.is_file() and p.suffix.lower() == ".xml"]
        if not usar_drive
        else []
    )
    if not usar_drive and not rutas_xml_locales:
        logger.warning("No hay archivos XML en la carpeta local: %s", carpeta)
        return json.dumps(
            {"ok": False, "error": "No hay XML en la carpeta de almacén"},
            ensure_ascii=False,
        )

    if not usar_drive:
        tiene_apoyo_local = any(
            p.is_file() and p.suffix.lower() in {".pdf", ".txt"} for p in carpeta.iterdir()
        )
        if not tiene_apoyo_local:
            if confirmar_solo_xml is False:
                return json.dumps(
                    {
                        "ok": True,
                        "reporte_generado": False,
                        "cancelado_por_usuario": True,
                        "mensaje": (
                            "Entendido, te sugiero revisar que hayas subido todos los documentos necesarios "
                            "(XML obligatorio, acompañado de su TXT o PDF de apoyo)."
                        ),
                    },
                    ensure_ascii=False,
                )
            if confirmar_solo_xml is None:
                pregunta = (
                    f"Oye, la entrada **{carpeta.name}** contiene solo archivos XML (sin TXT ni PDF de apoyo). "
                    "¿Olvidaste subirlos o no los tienes? Esto implica que el reporte no contendrá líneas ni "
                    "precios con factores. ¿Deseas generar el reporte solo con los XML proporcionados? (**y/n**)"
                )
                return json.dumps(
                    {
                        "ok": True,
                        "reporte_generado": False,
                        "requiere_confirmacion": True,
                        "tipo_confirmacion": "solo_xml",
                        "carpetas_solo_xml": [carpeta.name],
                        "pregunta_usuario": pregunta,
                        "pregunta_sugerida": pregunta,
                    },
                    ensure_ascii=False,
                )

        if guardar_factores and factores_elegidos:
            for linea_cod, factor_val in factores_elegidos.items():
                guardar_factor_personalizado(linea_cod, factor_val)

        pendientes_local = inspeccionar_pendientes_carpeta(
            rutas_xml_locales,
            carpeta,
            factores_elegidos=factores_elegidos,
            decisiones_rollos=decisiones_rollos_norm,
        )
        if pendientes_local["lineas_sin_factor"] or pendientes_local["rollos_pendientes"]:
            lista_lineas = pendientes_local["lineas_sin_factor"]
            lista_rollos = pendientes_local["rollos_pendientes"]
            if lista_lineas and lista_rollos:
                tipo_conf = "factores_y_rollos"
            elif lista_lineas:
                tipo_conf = "lineas_sin_factor"
            else:
                tipo_conf = "rollos_pendientes"
            pregunta = construir_pregunta_interactiva(lista_lineas, lista_rollos)
            return json.dumps(
                {
                    "ok": True,
                    "reporte_generado": False,
                    "requiere_confirmacion": True,
                    "tipo_confirmacion": tipo_conf,
                    "lineas_sin_factor": lista_lineas,
                    "rollos_pendientes": lista_rollos,
                    "menu_factores": (
                        formatear_menu_factores() if lista_lineas else None
                    ),
                    "pregunta_usuario": pregunta,
                    "pregunta_sugerida": pregunta,
                },
                ensure_ascii=False,
            )

    try:
        if not usar_drive:
            logger.info("Procesando carpeta local: %s", carpeta)
            procesar_carpeta(
                str(carpeta),
                factores_elegidos=factores_elegidos,
                decisiones_rollos=decisiones_rollos_norm,
            )
        ruta_resumen = carpeta / NOMBRE_ARCHIVO_RESUMEN
        if not ruta_resumen.is_file():
            logger.error("No se encontró el archivo de resumen esperado en %s", ruta_resumen)
            return json.dumps(
                {"ok": False, "error": "No se pudo generar el resumen de almacén"},
                ensure_ascii=False,
            )
        resumen = json.loads(ruta_resumen.read_text(encoding="utf-8"))
    except Exception as error:
        logger.exception("Error al leer resumen o procesar almacén: %s", error)
        return json.dumps(
            {"ok": False, "error": str(error)},
            ensure_ascii=False,
        )

    if usar_drive:
        resumen["origen"] = "google_drive"
        resumen["documentos_nuevos"] = sincronizacion["archivos"]
        resumen["carpetas_drive"] = sincronizacion["carpetas"]
        resumen["archivos_drive"] = sincronizacion["archivos"]
        if carpetas_reubicadas:
            resumen["carpetas_reubicadas"] = carpetas_reubicadas

    salida: dict = {
        "ok": True,
        "reporte_generado": True,
        "resumen": resumen,
    }
    if carpetas_reubicadas:
        salida["carpetas_reubicadas"] = carpetas_reubicadas
        salida["advertencia_ubicacion"] = construir_advertencia_ubicacion(
            carpetas_reubicadas
        )

    logger.info("Tool 'generar_entradas_almacen' completada exitosamente.")
    return json.dumps(salida, ensure_ascii=False)


@tool(args_schema=ActualizarPreciosReportesInput)
def actualizar_precios_reportes_generados(
    fecha: str | None = None,
    factores_elegidos: dict[str, str] | None = None,
) -> str:
    """Recalcula y aplica precios con factores y fórmulas en reportes Excel ya generados (en Google Drive y en la base local)."""
    try:
        resultado = actualizar_precios_reportes_drive(
            fecha=fecha,
            factores_elegidos=factores_elegidos,
        )
        return json.dumps(
            {
                "ok": True,
                "tipo": "actualizar_precios_reportes",
                **resultado,
            },
            ensure_ascii=False,
        )
    except Exception as error:
        logger.exception("Error al actualizar precios de reportes generados: %s", error)
        return json.dumps(
            {"ok": False, "tipo": "actualizar_precios_reportes", "error": str(error)},
            ensure_ascii=False,
        )


__all__ = [
    "consultar_almacen",
    "generar_entradas_almacen",
    "actualizar_precios_reportes_generados",
]
