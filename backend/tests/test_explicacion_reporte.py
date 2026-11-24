import json
from types import SimpleNamespace

import pandas as pd
import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.services.almacen.resumen import construir_resumen, explicar_procedencia_reporte


def test_procedencia_cuenta_todo_el_reporte_y_conserva_conversion_fuera_de_los_50_ejemplos():
    df = pd.DataFrame([
        {"Clave Artículo": str(i), "Línea": "FESTO", "PRECIO COMPRA": 20}
        for i in range(51)
    ])
    df.attrs["meta_por_clave"] = {
        str(i): {"origen_clave": "INVE02_EXACTO", "origen_linea": "INVE02", "factor": "FESTO"}
        for i in range(51)
    }
    df.attrs["meta_por_clave"]["50"]["divisor_metros"] = 50
    resumen = construir_resumen(df, duplicados_ignorados=2)
    assert len(resumen["productos_detalle"]) == 50
    explicacion = explicar_procedencia_reporte(resumen)
    assert "En 51 productos, tomé la línea del catálogo histórico de SAE" in explicacion
    assert "0 → FESTO" in explicacion
    assert "50 (50 m)" in explicacion
    assert "FESTO con el factor FESTO" in explicacion
    assert "Consolidé 2 filas repetidas" in explicacion


def test_explicacion_distingue_historial_apoyo_y_codigo_original():
    resumen = {
        "trazabilidad_catalogo_sae": {
            "origen_linea": {"HISTORIAL_UNICA": 1, "TXT_APOYO": 1, "SIN_LINEA": 1},
            "origen_clave": {"CVES_ALTER02": 1},
        },
        "productos_detalle": [
            {"clave_articulo": "D62-04", "linea": "UF", "trazabilidad_sae": {
                "origen_linea": "HISTORIAL_UNICA", "origen_clave": "CVES_ALTER02",
                "codigo_xml_original": "UQ62-DOT-04",
            }}
        ],
    }
    texto = explicar_procedencia_reporte(resumen)
    assert "única línea registrada en el historial" in texto
    assert "TXT o PDF de apoyo" in texto
    assert "la línea quedó pendiente" in texto
    assert "UQ62-DOT-04 → D62-04" in texto
    assert explicar_procedencia_reporte({}) == ""


@pytest.mark.parametrize("generado", [True, False])
def test_chat_publica_y_guarda_explicacion_solo_tras_generar_reporte(monkeypatch, tmp_path, generado):
    from app.api.v1.routes import chat
    from app.schemas.chat import ChatRequest
    from app.services import revision_reportes

    guardadas = []
    monkeypatch.setattr(chat, "CARPETA_DATOS", tmp_path)
    monkeypatch.setattr(chat, "_obtener_mensajes_previos_bd", lambda *args: [])
    monkeypatch.setattr(chat, "recuperar_operaciones_drive", lambda *args: "")
    monkeypatch.setattr(chat, "_guardar_interaccion_en_bd",
                        lambda **kwargs: guardadas.append(kwargs["respuesta_chat"].respuesta))
    monkeypatch.setattr(revision_reportes, "revision_actual", lambda *args: None)
    resumen = {
        "trazabilidad_catalogo_sae": {"origen_linea": {"INVE02": 1}},
        "productos_detalle": [{"clave_articulo": "197385", "linea": "FESTO",
                              "trazabilidad_sae": {"origen_linea": "INVE02"}}],
    }
    datos = dict(ok=True, reporte_generado=generado, resumen=resumen)
    if not generado:
        datos["requiere_confirmacion"] = True
    mensajes = [
        HumanMessage(content="Genera el reporte"),
        ToolMessage(name="generar_entradas_almacen", tool_call_id="reporte",
                    content=json.dumps(datos)),
        AIMessage(content="Revisa el resultado."),
    ]
    monkeypatch.setattr(chat, "grafo", SimpleNamespace(invoke=lambda *args, **kwargs: {"messages": mensajes}))
    respuesta = chat._ejecutar_chat(ChatRequest(mensaje="Genera el reporte", session_id="procedencia"))
    assert ("197385 → FESTO" in respuesta.respuesta) is generado
    assert ("Cómo se preparó este reporte" in guardadas[0]) is generado
