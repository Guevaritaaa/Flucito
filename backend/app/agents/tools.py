"""Tools disponibles para agente Flucito."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from langchain_core.tools import tool

from app.core.config import settings
from app.services.almacen.excel import (
    CARPETA_DATOS,
    NOMBRE_ARCHIVO_RESUMEN,
    actualizar_precios_reporte_existente,
    procesar_carpeta,
)
from app.services.almacen.factores import (
    formatear_menu_factores,
    guardar_factor_personalizado,
)
from app.services.almacen.fuentes.sincronizador import (
    actualizar_precios_reportes_drive,
    construir_pregunta_interactiva,
    inspeccionar_pendientes_carpeta,
    sincronizar_drive,
)
from app.services.almacen.fuentes.google_drive_client import (
    buscar_reportes_historicos,
    normalizar_fecha_reporte,
)
from app.services.almacen.fuentes.organizador import (
    construir_advertencia_ubicacion,
    mover_carpetas_con_reportes_drive,
    ordenar_todo_drive,
    revisar_carpetas_sin_reportes_drive,
)

logger = logging.getLogger(__name__)


@tool
def buscar_reporte_historico(fecha: str) -> str:
    """Busca reportes Excel de almacén guardados en Google Drive para una fecha de carga.

    Acepta DD-MM-AAAA, DD/MM/AAAA o AAAA-MM-DD. Úsala cuando pidan consultar o
    descargar un reporte anterior, no para generar el reporte actual.
    """
    try:
        fecha_normalizada = normalizar_fecha_reporte(fecha)
        reportes = buscar_reportes_historicos(fecha)
    except ValueError as error:
        return json.dumps(
            {"ok": False, "tipo": "busqueda_historica", "error": str(error)},
            ensure_ascii=False,
        )
    except (OSError, RuntimeError) as error:
        logger.exception("Error al buscar reportes históricos en Drive: %s", error)
        return json.dumps(
            {"ok": False, "tipo": "busqueda_historica", "error": str(error)},
            ensure_ascii=False,
        )
    except Exception as error:
        logger.exception("Fallo inesperado al buscar reportes históricos en Drive")
        return json.dumps(
            {"ok": False, "tipo": "busqueda_historica", "error": str(error)},
            ensure_ascii=False,
        )

    return json.dumps(
        {
            "ok": True,
            "tipo": "busqueda_historica",
            "fecha": fecha_normalizada,
            "reportes": reportes,
        },
        ensure_ascii=False,
    )


def _normalizar_decisiones_rollos(
    cambiar_xro_a_mtr: bool | None,
    dividir_precio_entre_metros: bool | None,
    decisiones_rollos: dict[str, dict[str, object]] | None,
) -> dict[str, dict[str, object]] | None:
    """Combina banderas globales de rollo/metros con decisiones por clave de artículo."""
    combinadas: dict[str, dict[str, object]] = {
        str(k): dict(v) for k, v in (decisiones_rollos or {}).items() if isinstance(v, dict)
    }
    if cambiar_xro_a_mtr is not None or dividir_precio_entre_metros is not None:
        comodin = dict(combinadas.get("*", {}))
        if cambiar_xro_a_mtr is not None:
            comodin["cambiar_a_mtr"] = bool(cambiar_xro_a_mtr)
        if dividir_precio_entre_metros is not None:
            comodin["dividir_entre_metros"] = bool(dividir_precio_entre_metros)
        combinadas["*"] = comodin
    return combinadas or None


@tool
def generar_entradas_almacen(
    confirmar_solo_xml: bool | None = None,
    factores_elegidos: dict[str, str] | None = None,
    guardar_factores: bool | None = None,
    cambiar_xro_a_mtr: bool | None = None,
    dividir_precio_entre_metros: bool | None = None,
    decisiones_rollos: dict[str, dict[str, object]] | None = None,
) -> str:
    """Genera Excel acumulativo y resumen JSON desde local o Google Drive.

    Parámetros opcionales (úsalos cuando el usuario responda a una confirmación previa):
    - confirmar_solo_xml: True ('y') si el usuario autoriza generar solo con XML; False ('n') si cancela.
    - factores_elegidos: Diccionario {CODIGO_LINEA: NUMERO_O_NOMBRE_FACTOR} para líneas sin factor definido.
    - guardar_factores: True ('y') si el usuario desea guardar los factores elegidos para futuras compras.
    - cambiar_xro_a_mtr: True ('y') o False ('n') para cambiar la unidad XRO a MTR en rollos/carretes.
    - dividir_precio_entre_metros: True ('y') o False ('n') para dividir el precio de compra entre los metros.
    - decisiones_rollos: Diccionario opcional por clave de artículo {"CLAVE": {"cambiar_a_mtr": bool, "dividir_entre_metros": bool}}.
    """
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
            ruta_resumen = Path(CARPETA_DATOS) / NOMBRE_ARCHIVO_RESUMEN
            ruta_base = Path(CARPETA_DATOS) / "BASE_ENTRADAS_ALMACEN.xlsx"
            if ruta_base.is_file():
                try:
                    actualizar_precios_reporte_existente(
                        str(ruta_base),
                        carpeta_apoyo=str(CARPETA_DATOS),
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
                    {"ok": False, "error": "No hay subcarpetas con documentos en Google Drive y no hay base generada."},
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
    carpeta = Path(CARPETA_DATOS)
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


@tool
def actualizar_precios_reportes_generados(
    fecha: str | None = None,
    factores_elegidos: dict[str, str] | None = None,
) -> str:
    """Revisa los reportes Excel ya generados (en Google Drive y en la base local) y si detecta que no tienen los precios o fórmulas aplicadas, se los calcula y actualiza.

    Úsala cuando el usuario pida aplicar, calcular o actualizar los precios de los reportes ya generados.
    """
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


@tool
def revisar_carpetas_sin_reportes() -> str:
    """Inspecciona y lista qué carpetas en Google Drive tienen XMLs o TXTs pendientes sin reporte Excel generado.

    Úsala cuando el usuario pida 'Revisar carpetas sin reportes' o consultar qué carpetas faltan por procesar.
    """
    try:
        resultado = revisar_carpetas_sin_reportes_drive()
        return json.dumps(resultado, ensure_ascii=False)
    except Exception as error:
        logger.exception("Error al revisar carpetas sin reportes en Drive: %s", error)
        return json.dumps(
            {"ok": False, "tipo": "revisar_carpetas_sin_reportes", "error": str(error)},
            ensure_ascii=False,
        )


@tool
def ordenar_todo() -> str:
    """Ordena todas las carpetas y archivos en Google Drive.

    Reubica carpetas sin reporte mal puestas en DOCUMENTOS ENTRADA hacia ENTRADAS AL INVENTARIO,
    mueve carpetas con reportes a su lugar, acomoda archivos sueltos y limpia carpetas vacías.
    Úsala cuando el usuario pida 'Ordenar todo' u organizar las carpetas de Drive.
    """
    try:
        resultado = ordenar_todo_drive()
        return json.dumps(resultado, ensure_ascii=False)
    except Exception as error:
        logger.exception("Error al ordenar carpetas en Drive: %s", error)
        return json.dumps(
            {"ok": False, "tipo": "ordenar_todo", "error": str(error)},
            ensure_ascii=False,
        )


@tool
def mover_carpetas_con_reportes() -> str:
    """Traslada al archivo (DOCUMENTOS ENTRADA) las carpetas de ENTRADAS AL INVENTARIO que ya fueron procesadas y tienen reporte Excel.

    Úsala cuando el usuario pida 'Mover carpetas con reportes a su lugar' o archivar carpetas ya procesadas.
    """
    try:
        resultado = mover_carpetas_con_reportes_drive()
        return json.dumps(resultado, ensure_ascii=False)
    except Exception as error:
        logger.exception("Error al mover carpetas con reportes en Drive: %s", error)
        return json.dumps(
            {"ok": False, "tipo": "mover_carpetas_con_reportes", "error": str(error)},
            ensure_ascii=False,
        )


@tool
def preparar_entorno_pruebas() -> str:
    """Prepara y restaura el entorno de pruebas en Google Drive.
    
    Usa esta herramienta ÚNICAMENTE cuando el usuario pida explícitamente restaurar el entorno de pruebas,
    borrar los reportes generados y regresar todos los archivos originales a 'ENTRADAS AL INVENTARIO' para correr pruebas de nuevo.
    """
    try:
        from app.services.almacen.fuentes.limpieza import restaurar_entorno_pruebas
        res = restaurar_entorno_pruebas()
        return json.dumps(res, ensure_ascii=False)
    except Exception as e:
        logger.exception("Error al restaurar entorno de pruebas: %s", e)
        return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)
