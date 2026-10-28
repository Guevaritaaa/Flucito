"""Pruebas unitarias y de integración para las 6 herramientas del agente Flucito."""

from __future__ import annotations

import json
from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
import pandas as pd
import pytest
from pydantic import ValidationError

from app.agents import tools
from app.agents.tools import (
    HERRAMIENTAS,
    actualizar_precios_reportes_generados,
    almacen_tools,
    consultar_almacen,
    consultar_drive,
    drive_tools,
    generar_entradas_almacen,
    gestionar_archivos_drive,
    preparar_entorno_pruebas,
)
from app.agents.tools.schemas import (
    ConsultarAlmacenInput,
    ConsultarDriveInput,
    GestionarArchivosDriveInput,
)
from app.api.v1.routes import chat as chat_route
from app.schemas.chat import ChatRequest


def test_lista_herramientas_contiene_exactamente_las_6_tools_ortogonales() -> None:
    """Verifica que HERRAMIENTAS exponga exactamente las 6 herramientas orientadas a recursos."""
    nombres = [herramienta.name for herramienta in HERRAMIENTAS]
    assert nombres == [
        "consultar_drive",
        "gestionar_archivos_drive",
        "consultar_almacen",
        "generar_entradas_almacen",
        "actualizar_precios_reportes_generados",
        "preparar_entorno_pruebas",
    ]


def test_esquemas_pydantic_planos_validan_literales_y_limitan_parametros() -> None:
    """Verifica que los esquemas Pydantic sean planos (sin submodelos anidados) y rechacen valores fuera de Literal."""
    for herramienta in HERRAMIENTAS:
        esquema = herramienta.args_schema.model_json_schema()
        propiedades = esquema.get("properties", {})
        assert "$defs" not in esquema, (
            f"La herramienta {herramienta.name} no debe tener submodelos anidados ($defs)"
        )
        assert len(propiedades) <= 7, (
            f"La herramienta {herramienta.name} excede el límite de parámetros planos"
        )

    with pytest.raises(ValidationError):
        ConsultarDriveInput(modo_consulta="modo_inexistente")  # type: ignore[arg-type]

    with pytest.raises(ValidationError):
        GestionarArchivosDriveInput(accion="accion_inexistente")  # type: ignore[arg-type]

    with pytest.raises(ValidationError):
        ConsultarAlmacenInput(tipo_consulta="consulta_inexistente")  # type: ignore[arg-type]


def test_consultar_drive_modos_explorar_auditar_y_buscar_reportes(monkeypatch) -> None:
    """Verifica que consultar_drive despache correctamente cada modo de lectura."""
    monkeypatch.setattr(
        drive_tools,
        "explorar_estructura_drive",
        lambda **kwargs: {
            "ok": True,
            "tipo": "explorar_estructura",
            "ubicacion_consultada": kwargs["ubicacion"],
        },
    )
    monkeypatch.setattr(
        drive_tools,
        "auditar_facturas_drive",
        lambda **kwargs: {
            "ok": True,
            "tipo": "auditar_facturas",
            "filtro_auditoria": kwargs["filtro_auditoria"],
            "resumen_hallazgos": {"carpetas_sin_xml": ["ENTRADAS AL INVENTARIO/20-03-2026"]},
        },
    )
    monkeypatch.setattr(
        drive_tools,
        "buscar_reportes_historicos",
        lambda fecha=None, proveedor=None: [
            {"id": "rep-1", "nombre": "ENTRADAS_ALMACEN_18-03-2026.xlsx", "fecha": "18-03-2026"}
        ],
    )

    resp_explorar = json.loads(
        consultar_drive.invoke(
            {"modo_consulta": "explorar_estructura", "ubicacion": "entradas_al_inventario"}
        )
    )
    assert resp_explorar["ok"] is True
    assert resp_explorar["ubicacion_consultada"] == "entradas_al_inventario"

    resp_auditar = json.loads(
        consultar_drive.invoke(
            {"modo_consulta": "auditar_facturas", "filtro_auditoria": "sin_xml"}
        )
    )
    assert resp_auditar["ok"] is True
    assert resp_auditar["filtro_auditoria"] == "sin_xml"
    assert resp_auditar["resumen_hallazgos"]["carpetas_sin_xml"] == [
        "ENTRADAS AL INVENTARIO/20-03-2026"
    ]

    resp_reportes = json.loads(
        consultar_drive.invoke(
            {
                "modo_consulta": "buscar_reportes_excel",
                "carpeta_o_fecha": "2026-03-18",
                "proveedor": "Festo",
            }
        )
    )
    assert resp_reportes["ok"] is True
    assert resp_reportes["tipo"] == "busqueda_historica"
    assert resp_reportes["fecha"] == "18-03-2026"
    assert len(resp_reportes["reportes"]) == 1


def test_gestionar_archivos_drive_acciones_masivas_y_puntuales(monkeypatch) -> None:
    """Verifica que gestionar_archivos_drive ejecute tanto acciones masivas como puntuales por ruta."""
    monkeypatch.setattr(
        drive_tools,
        "ordenar_todo_drive",
        lambda: {"ok": True, "tipo": "ordenar_todo", "carpetas_reubicadas": ["20-03-2026"]},
    )
    monkeypatch.setattr(
        drive_tools,
        "mover_elemento_por_ruta",
        lambda ruta_origen, ruta_destino: {
            "ok": True,
            "tipo": "mover_elemento",
            "movido": True,
            "origen_anterior": ruta_origen,
            "nueva_ruta": f"{ruta_destino}/{ruta_origen}",
        },
    )
    monkeypatch.setattr(
        drive_tools,
        "crear_carpeta_por_ruta",
        lambda ruta_nueva_carpeta: {
            "ok": True,
            "tipo": "crear_carpeta",
            "creada": True,
            "ruta_completa": ruta_nueva_carpeta,
        },
    )
    monkeypatch.setattr(
        drive_tools,
        "eliminar_elemento_por_ruta",
        lambda ruta_objetivo, confirmar_eliminar_con_contenido=False: {
            "ok": confirmar_eliminar_con_contenido,
            "requiere_confirmacion": not confirmar_eliminar_con_contenido,
            "tipo": "eliminar_elemento",
            "ruta_objetivo": ruta_objetivo,
        },
    )

    res_ordenar = json.loads(
        gestionar_archivos_drive.invoke({"accion": "organizar_todo"})
    )
    assert res_ordenar["ok"] is True
    assert res_ordenar["tipo"] == "ordenar_todo"

    res_mover = json.loads(
        gestionar_archivos_drive.invoke(
            {
                "accion": "mover_elemento",
                "ruta_origen": "18-03-2026",
                "ruta_destino": "DOCUMENTOS ENTRADA",
            }
        )
    )
    assert res_mover["ok"] is True
    assert res_mover["movido"] is True

    res_crear = json.loads(
        gestionar_archivos_drive.invoke(
            {
                "accion": "crear_carpeta",
                "ruta_destino": "ENTRADAS AL INVENTARIO/28-03-2026",
            }
        )
    )
    assert res_crear["ok"] is True
    assert res_crear["creada"] is True

    res_eliminar_bloqueado = json.loads(
        gestionar_archivos_drive.invoke(
            {
                "accion": "eliminar_elemento",
                "ruta_origen": "18-03-2026",
                "confirmar_eliminar_con_contenido": False,
            }
        )
    )
    assert res_eliminar_bloqueado["ok"] is False
    assert res_eliminar_bloqueado["requiere_confirmacion"] is True


def test_consultar_almacen_resumen_busqueda_y_factores(monkeypatch, tmp_path: Path) -> None:
    """Verifica los tres modos de consultar_almacen sobre datos locales y catálogo de factores."""
    monkeypatch.setattr(tools, "CARPETA_DATOS", tmp_path)

    # 1. Catálogo de factores para una línea específica
    res_factor = json.loads(
        consultar_almacen.invoke(
            {"tipo_consulta": "catalogo_factores", "linea": "FESTO"}
        )
    )
    assert res_factor["ok"] is True
    assert res_factor["factor_asignado"] == "FESTO"
    assert res_factor["formulas_precio"]["PUBLICO"] == "{COSTEO}/.7"

    # 2. Resumen general cuando existe BASE_ENTRADAS_ALMACEN_RESUMEN.json
    ruta_resumen = tmp_path / "BASE_ENTRADAS_ALMACEN_RESUMEN.json"
    ruta_resumen.write_text(
        json.dumps({"total_registros": 5, "proveedores": ["FESTO PNEUMATIC SA"]}),
        encoding="utf-8",
    )
    res_resumen = json.loads(
        consultar_almacen.invoke({"tipo_consulta": "resumen_general"})
    )
    assert res_resumen["ok"] is True
    assert res_resumen["tiene_datos"] is True
    assert res_resumen["resumen"]["total_registros"] == 5

    # 3. Buscar entradas filtrando por proveedor y línea en BASE_ENTRADAS_ALMACEN.xlsx
    ruta_base = tmp_path / "BASE_ENTRADAS_ALMACEN.xlsx"
    df = pd.DataFrame(
        [
            {
                "Clave Artículo": "CIL-01",
                "DESCRIPCION": "CILINDRO NEUMATICO",
                "Línea": "FESTO",
                "PROVEEDOR": "FESTO PNEUMATIC SA",
                "PRECIO COMPRA": 500.0,
                "FOLIO": "101",
            },
            {
                "Clave Artículo": "MANG-02",
                "DESCRIPCION": "MANGUERA HIDRAULICA",
                "Línea": "PKRH",
                "PROVEEDOR": "PARKER HANNIFIN",
                "PRECIO COMPRA": 300.0,
                "FOLIO": "102",
            },
        ]
    )
    df.to_excel(ruta_base, index=False)

    res_busqueda = json.loads(
        consultar_almacen.invoke(
            {
                "tipo_consulta": "buscar_entradas",
                "proveedor": "FESTO",
            }
        )
    )
    assert res_busqueda["ok"] is True
    assert res_busqueda["total_coincidencias"] == 1
    assert res_busqueda["entradas"][0]["Clave Artículo"] == "CIL-01"


def test_generar_entradas_actualizar_precios_y_preparar_pruebas(
    monkeypatch, tmp_path: Path
) -> None:
    """Verifica el despacho de generar_entradas_almacen, actualizar_precios_reportes_generados y preparar_entorno_pruebas."""
    monkeypatch.setattr(tools, "CARPETA_DATOS", tmp_path)
    monkeypatch.setattr(almacen_tools.settings, "google_drive_folder_id", "folder-root")
    monkeypatch.setattr(almacen_tools.settings, "google_service_account_json", '{"type": "service_account"}')

    ruta_resumen = tmp_path / "BASE_ENTRADAS_ALMACEN_RESUMEN.json"
    ruta_resumen.write_text(
        json.dumps({"total_registros": 3, "proveedores": ["FESTO"]}),
        encoding="utf-8",
    )

    parametros_recibidos: dict = {}

    def falso_sincronizar(**kwargs):
        parametros_recibidos.update(kwargs)
        return {
            "carpetas": 1,
            "carpetas_nuevas": 1,
            "archivos": 2,
            "carpetas_reubicadas": ["18-03-2026"],
        }

    monkeypatch.setattr(almacen_tools, "sincronizar_drive", falso_sincronizar)
    monkeypatch.setattr(
        almacen_tools,
        "actualizar_precios_reportes_drive",
        lambda **kwargs: {
            "reportes_actualizados": 2,
            "base_local_actualizada": True,
        },
    )
    from app.services.almacen.fuentes import limpieza

    monkeypatch.setattr(
        limpieza,
        "restaurar_entorno_pruebas",
        lambda: {
            "ok": True,
            "reportes_eliminados": 4,
            "carpetas_movidas": 1,
        },
    )

    res_generar = json.loads(
        generar_entradas_almacen.invoke(
            {
                "confirmar_solo_xml": True,
                "factores_elegidos": {"FESTO": "1"},
            }
        )
    )
    assert res_generar["ok"] is True
    assert res_generar["reporte_generado"] is True
    assert res_generar["carpetas_reubicadas"] == ["18-03-2026"]
    assert parametros_recibidos["confirmar_solo_xml"] is True
    assert parametros_recibidos["factores_elegidos"] == {"FESTO": "1"}

    res_precios = json.loads(
        actualizar_precios_reportes_generados.invoke(
            {"fecha": "18-03-2026", "factores_elegidos": {"FESTO": "1"}}
        )
    )
    assert res_precios["ok"] is True
    assert res_precios["reportes_actualizados"] == 2

    res_pruebas = json.loads(preparar_entorno_pruebas.invoke({}))
    assert res_pruebas["ok"] is True
    assert res_pruebas["reportes_eliminados"] == 4


def test_chat_endpoint_integra_avisos_y_bloqueo_de_confirmacion_con_nuevas_tools(monkeypatch) -> None:
    """Verifica que _ejecutar_chat procese avisos de ubicación y bloqueos de confirmación de las nuevas tools."""
    class GrafoFalso:
        def invoke(self, estado, config=None):
            return {
                "messages": [
                    HumanMessage(content="Elimina la carpeta 18-03-2026"),
                    AIMessage(
                        content="",
                        tool_calls=[
                            {
                                "name": "gestionar_archivos_drive",
                                "args": {"accion": "eliminar_elemento", "ruta_origen": "18-03-2026"},
                                "id": "call_del",
                            }
                        ],
                    ),
                    ToolMessage(
                        content=json.dumps(
                            {
                                "ok": False,
                                "requiere_confirmacion": True,
                                "tipo": "eliminar_elemento",
                                "pregunta_usuario": "La carpeta contiene 3 archivos. ¿Confirmas eliminarla?",
                            }
                        ),
                        tool_call_id="call_del",
                    ),
                    AIMessage(
                        content="La carpeta **18-03-2026** contiene 3 archivos. ¿Confirmas que deseas eliminarla?"
                    ),
                ]
            }

    monkeypatch.setattr(chat_route, "grafo", GrafoFalso())
    respuesta = chat_route._ejecutar_chat(
        ChatRequest(mensaje="Elimina la carpeta 18-03-2026", session_id="ses-test")
    )
    assert "contiene 3 archivos" in respuesta.respuesta
    assert respuesta.archivo_almacen_url is None
