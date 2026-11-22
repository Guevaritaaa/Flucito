import time
from langchain_core.messages import AIMessage

from app.api.v1.routes import chat as chat_route
from app.api.v1.routes.chat import contenido_a_texto
from app.schemas.chat import ChatRequest, ChatResponse


def test_contenido_a_texto_normaliza_responses_api() -> None:
    mensaje = AIMessage(content=[{"type": "text", "text": "Respuesta Luna"}])

    assert contenido_a_texto(mensaje) == "Respuesta Luna"


def test_chat_async_y_status_completan_sin_timeout(monkeypatch) -> None:
    monkeypatch.setattr(
        chat_route,
        "_ejecutar_chat",
        lambda req: ChatResponse(
            respuesta=f"Procesado: {req.mensaje}",
            archivo_almacen_url="/api/v1/almacen/download",
        ),
    )

    creado = chat_route.iniciar_chat_async(ChatRequest(mensaje="Generar reportes", session_id="s-1"))
    assert creado.job_id

    estado = None
    for _ in range(20):
        estado = chat_route.consultar_estado_chat(creado.job_id)
        if estado.status == "completed":
            break
        time.sleep(0.05)

    assert estado is not None
    assert estado.status == "completed"
    assert estado.result is not None
    assert estado.result.respuesta == "Procesado: Generar reportes"
    assert estado.result.archivo_almacen_url == "/api/v1/almacen/download"



def test_actividad_real_se_publica_y_se_guarda(monkeypatch) -> None:
    from uuid import uuid4

    job_id = "actividad-test"
    chat_route._JOBS[job_id] = {"status": "running", "result": None, "error": None}
    chat_route._CONTEXTO_JOB.job_id = job_id
    guardadas = []
    monkeypatch.setattr(chat_route, "_obtener_mensajes_previos_bd", lambda *args: [])
    monkeypatch.setattr(chat_route, "_guardar_interaccion_en_bd", lambda **kwargs: guardadas.append(kwargs["respuesta_chat"]))

    class GrafoSimulado:
        def invoke(self, estado, config):
            handler = config["callbacks"][0]
            model_id, tool_id = uuid4(), uuid4()
            handler.on_chat_model_start({}, [], run_id=model_id)
            assert chat_route.consultar_estado_chat(job_id).etapa == "pensando"
            handler.on_llm_end(None, run_id=model_id)
            handler.on_tool_start({"name": "consultar_drive"}, "datos privados", run_id=tool_id)
            estado_job = chat_route.consultar_estado_chat(job_id)
            assert estado_job.etapa == "trabajando"
            assert estado_job.actividades[-1].texto == "Consultando Drive"
            assert "datos privados" not in str(estado_job.actividades)
            handler.on_tool_end(None, run_id=tool_id)
            return {"messages": [AIMessage(content="Terminado")]}

    monkeypatch.setattr(chat_route, "grafo", GrafoSimulado())
    try:
        respuesta = chat_route._ejecutar_chat(ChatRequest(mensaje="Hola", session_id="s"))
        assert [a.estado for a in respuesta.actividades] == ["completado", "completado"]
        assert guardadas[0].actividades == respuesta.actividades
    finally:
        del chat_route._CONTEXTO_JOB.job_id
        chat_route._JOBS.pop(job_id, None)


def test_actividades_son_opcionales_en_historial_anterior() -> None:
    from datetime import datetime
    from app.schemas.chat import MensajeChatOut

    mensaje = MensajeChatOut(id=1, rol="assistant", contenido="Hola", creado_en=datetime.now())
    assert mensaje.actividades == []


def test_callback_recibe_eventos_reales_de_langgraph() -> None:
    from typing import TypedDict
    from langchain_core.language_models.fake_chat_models import FakeListChatModel
    from langchain_core.tools import tool
    from langgraph.graph import END, StateGraph

    @tool
    def consultar_drive() -> str:
        """Consulta Drive."""
        return "ok"

    class Estado(TypedDict):
        respuesta: str

    modelo = FakeListChatModel(responses=["listo"])

    def nodo(estado):
        modelo.invoke("hola")
        consultar_drive.invoke({})
        return {"respuesta": "listo"}

    builder = StateGraph(Estado)
    builder.add_node("nodo", nodo)
    builder.set_entry_point("nodo")
    builder.add_edge("nodo", END)
    handler = chat_route.ActividadHandler()
    builder.compile().invoke({"respuesta": ""}, config={"callbacks": [handler]})
    assert [item["texto"] for item in handler.actividades] == [
        "Analizando la solicitud", "Consultando Drive"
    ]
    assert all(item["estado"] == "completado" for item in handler.actividades)


def test_stream_langgraph_publica_texto_y_funciones_sin_parametros() -> None:
    from typing import TypedDict
    from langchain_core.language_models.fake_chat_models import FakeListChatModel
    from langchain_core.tools import tool
    from langgraph.graph import END, StateGraph

    @tool
    def consultar_drive() -> str:
        """Consulta Drive."""
        return "resultado privado"

    class Estado(TypedDict):
        respuesta: str

    def nodo(estado):
        consultar_drive.invoke({})
        resultado = FakeListChatModel(responses=["Hola mundo"]).invoke("hola")
        return {"respuesta": resultado.content}

    builder = StateGraph(Estado)
    builder.add_node("nodo", nodo)
    builder.set_entry_point("nodo")
    builder.add_edge("nodo", END)
    handler = chat_route.ActividadHandler()
    list(builder.compile().stream({"respuesta": ""}, config={"callbacks": [handler]}, stream_mode=["messages", "values"]))
    assert handler.texto_provisional == "Hola mundo"
    assert handler.actividades[0]["funcion"] == "consultar_drive"
    assert handler.actividades[0]["tipo"] == "funcion"
    assert "resultado privado" not in str(handler.actividades)


def test_texto_provisional_se_descarta_al_llamar_funcion() -> None:
    from uuid import uuid4
    from langchain_core.messages import AIMessageChunk
    from langchain_core.outputs import ChatGenerationChunk

    handler = chat_route.ActividadHandler()
    run_id = uuid4()
    handler.on_chat_model_start({}, [], run_id=run_id)
    handler.on_llm_new_token("Voy a revisar", run_id=run_id)
    assert handler.texto_provisional == "Voy a revisar"
    chunk = ChatGenerationChunk(message=AIMessageChunk(content="", tool_call_chunks=[{"name": "consultar_drive", "args": "", "id": "call-1", "index": 0}]))
    handler.on_llm_new_token("", chunk=chunk, run_id=run_id)
    handler.on_llm_new_token("oculto", run_id=run_id)
    assert handler.texto_provisional == ""


def test_estado_de_tarea_verifica_propietario() -> None:
    from types import SimpleNamespace
    import pytest
    from fastapi import HTTPException

    chat_route._JOBS["privado"] = {"status": "running", "result": None, "error": None, "usuario_id": 1}
    try:
        with pytest.raises(HTTPException) as error:
            chat_route.consultar_estado_chat("privado", SimpleNamespace(id=2))
        assert error.value.status_code == 403
        assert chat_route.consultar_estado_chat("privado", SimpleNamespace(id=1)).status == "running"
    finally:
        chat_route._JOBS.pop("privado", None)


def test_stream_de_tarea_entrega_snapshot_final_sin_repetir_trabajo() -> None:
    import asyncio
    import json

    job_id = "stream-terminado"
    chat_route._JOBS[job_id] = {
        "status": "completed", "result": ChatResponse(respuesta="Listo"),
        "error": None, "usuario_id": None, "texto_provisional": "Listo",
        "actividades": [{"id": "1", "tipo": "funcion", "funcion": "consultar_drive", "texto": "Consultando Drive", "estado": "completado"}],
    }

    async def leer():
        response = chat_route.eventos_chat(job_id, None)
        return [item async for item in response.body_iterator]

    try:
        primer = asyncio.run(leer())
        segundo = asyncio.run(leer())
        assert primer == segundo
        payload = json.loads(primer[0][len("data: "):])
        assert payload["result"]["respuesta"] == "Listo"
        assert payload["actividades"][0]["funcion"] == "consultar_drive"
    finally:
        chat_route._JOBS.pop(job_id, None)


def test_actividad_conserva_descripcion_publica_sin_invocar_modelo(monkeypatch) -> None:
    from uuid import uuid4
    from app.agents import graph

    class Modelo:
        def invoke(self, mensajes):
            raise AssertionError("Las etiquetas no deben invocar modelos")

    monkeypatch.setattr(graph, "llm_primario", Modelo())
    handler = chat_route.ActividadHandler()
    handler.on_tool_start({"name": "consultar_drive"}, "datos privados", run_id=uuid4())
    assert handler.actividades[0]["texto"] == "Consultando Drive"
    assert "datos privados" not in str(handler.actividades)


def _chat_con_resultado(monkeypatch, pregunta, datos, respuesta, anteriores=None):
    import json
    from langchain_core.messages import HumanMessage, ToolMessage

    class GrafoFalso:
        def invoke(self, estado, config):
            return {"messages": [*(anteriores or []), HumanMessage(content=pregunta), ToolMessage(content=json.dumps(datos), tool_call_id="tool"), AIMessage(content=respuesta)]}

    monkeypatch.setattr(chat_route, "grafo", GrafoFalso())
    monkeypatch.setattr(chat_route, "_obtener_mensajes_previos_bd", lambda *args: [])
    monkeypatch.setattr(chat_route, "_guardar_interaccion_en_bd", lambda **kwargs: None)
    return chat_route._ejecutar_chat(ChatRequest(mensaje=pregunta, session_id="prueba"))


def test_ultima_carpeta_solo_adjunta_reportes_de_fecha_reciente(monkeypatch):
    datos = {"ok": True, "tipo": "busqueda_historica", "reportes": [
        {"id": "viejo", "nombre": "viejo.xlsx", "fecha": "14-11-2026"},
        {"id": "nuevo1", "nombre": "nuevo.xlsx", "fecha": "17-11-2026"},
        {"id": "nuevo2", "nombre": "proveedor.xlsx", "fecha": "17-11-2026"},
    ]}
    respuesta = _chat_con_resultado(monkeypatch, "cual es la ultima carpeta de reportes que tienes", datos, "Hay 72 reportes")
    assert [r["nombre"] for r in respuesta.reportes_historicos] == ["nuevo.xlsx", "proveedor.xlsx"]
    assert "17-11-2026" in respuesta.respuesta
    assert "viejo.xlsx" not in respuesta.respuesta


def test_busqueda_historica_filtra_fecha_explicita_y_fecha_invalida(monkeypatch):
    datos = {"ok": True, "tipo": "busqueda_historica", "reportes": [
        {"id": "uno", "nombre": "uno.xlsx", "fecha": "14-11-2026"},
        {"id": "dos", "nombre": "dos.xlsx", "fecha": "17-11-2026"},
    ]}
    respuesta = _chat_con_resultado(monkeypatch, "descarga el reporte del 14-11-2026", datos, "Aquí tienes")
    assert [r["nombre"] for r in respuesta.reportes_historicos] == ["uno.xlsx"]
    assert respuesta.archivo_almacen_url is None
    respuesta = _chat_con_resultado(monkeypatch, "reporte del 99-99-2026", datos, "No es una fecha válida")
    assert respuesta.reportes_historicos == []


def test_archivos_solo_se_entregan_al_solicitarlos_o_generarse(monkeypatch, tmp_path):
    from app.services.almacen.excel import NOMBRE_ARCHIVO_BASE
    from app.services.almacen.txt_aspel import NOMBRE_TXT_COMAS, NOMBRE_TXT_TABS
    monkeypatch.setattr(chat_route, "CARPETA_DATOS", tmp_path)
    for nombre in (NOMBRE_ARCHIVO_BASE, NOMBRE_TXT_COMAS, NOMBRE_TXT_TABS):
        (tmp_path / nombre).write_text("datos")
    resultado = {"ok": True, "reporte_generado": True, "resumen": {"archivos": 1}}
    respuesta = _chat_con_resultado(monkeypatch, "genera el reporte", resultado, "El Excel está listo. ¿Deseas el TXT para Aspel?")
    assert respuesta.archivo_almacen_url and respuesta.archivo_txt_url is None
    respuesta = _chat_con_resultado(monkeypatch, "muéstrame los factores", {"ok": True}, "Para Aspel usa el botón de descarga.")
    assert respuesta.archivo_almacen_url is None and respuesta.archivo_txt_url is None
    respuesta = _chat_con_resultado(monkeypatch, "descarga el txt en tabulaciones", {"ok": True}, "Aquí tienes el archivo")
    assert respuesta.archivo_txt_url.endswith("tabs")


def test_solicitud_de_comas_como_respuesta_a_pregunta_previa(monkeypatch, tmp_path):
    from langchain_core.messages import HumanMessage
    from app.services.almacen.txt_aspel import NOMBRE_TXT_COMAS
    monkeypatch.setattr(chat_route, "CARPETA_DATOS", tmp_path)
    (tmp_path / NOMBRE_TXT_COMAS).write_text("datos")
    previos = [HumanMessage(content="genera reporte"), AIMessage(content="¿Quieres el TXT para Aspel en comas o tabulaciones?")]
    respuesta = _chat_con_resultado(monkeypatch, "comas", {"ok": True}, "Aquí tienes", anteriores=previos)
    assert respuesta.archivo_txt_url.endswith("comas")


def test_tabla_factores_preserva_formulas_de_herramienta(monkeypatch):
    datos = {"ok": True, "tipo_consulta": "catalogo_factores", "factores_disponibles": {"YPC": {"PUBLICO": "{COSTEO}/.6", "MINIMO": "({COSTEO}/.6)*.8", "MOSTRADOR": "{COSTEO}/.6", "MAYOREO": "({COSTEO}/.6)*.9", "DISTRIBUIDOR": "{PUBLICO}*.8"}}}
    respuesta = _chat_con_resultado(monkeypatch, "Muéstrame los factores de precio actuales", datos, "texto anterior")
    assert "| Factor | Público |" in respuesta.respuesta
    assert "`(COSTO/.6)*.8`" in respuesta.respuesta
    assert "`PUBLICO*.8`" in respuesta.respuesta


def test_avisos_xml_no_se_repiten_si_respuesta_ya_los_incluye(monkeypatch):
    datos = {"ok": True, "advertencia_xmls_sin_apoyo": "Las siguientes facturas no tenían archivos de apoyo"}
    respuesta = _chat_con_resultado(monkeypatch, "genera reporte", datos, "Estas facturas no tenían TXT o PDF de apoyo.")
    assert "Las siguientes facturas" not in respuesta.respuesta


def test_error_modelo_recuperado_se_distingue_de_error_definitivo():
    from uuid import uuid4
    handler = chat_route.ActividadHandler()
    a, b = uuid4(), uuid4()
    handler.on_chat_model_start({}, [], run_id=a)
    handler.on_llm_error(RuntimeError("temporal"), run_id=a)
    handler.on_chat_model_start({}, [], run_id=b)
    assert handler.actividades[0]["estado"] == "reintentando"
    handler.on_llm_end(None, run_id=b)
    assert handler.actividades[0]["estado"] == "recuperado"
    assert handler.actividades[1]["estado"] == "completado"

    handler.on_chat_model_start({}, [], run_id=a)
    handler.on_llm_error(RuntimeError("definitivo"), run_id=a)
    assert handler.actividades[-1]["estado"] == "error"


def test_consulta_general_de_carpetas_no_se_limita_a_raiz(monkeypatch):
    from langchain_core.messages import HumanMessage
    from app.agents import graph

    respuesta_modelo = AIMessage(content="", tool_calls=[{"name": "consultar_drive", "args": {"modo_consulta": "explorar_estructura", "ubicacion": "raiz"}, "id": "call"}])
    monkeypatch.setattr(graph, "invocar_con_fallback", lambda *args: respuesta_modelo)
    resultado = graph.nodo_flucito({"messages": [HumanMessage(content="¿qué carpetas hay en Drive?")]})
    assert resultado["messages"][0].tool_calls[0]["args"]["ubicacion"] == "todas"
    resultado = graph.nodo_flucito({"messages": [HumanMessage(content="¿qué carpetas hay en la raíz?")]})
    assert resultado["messages"][0].tool_calls[0]["args"]["ubicacion"] == "raiz"


def test_etiquetas_de_actividad_no_lanzan_llamadas_auxiliares(monkeypatch):
    from uuid import uuid4
    def prohibido(*args, **kwargs):
        raise AssertionError("Las etiquetas no deben lanzar hilos ni modelos")
    monkeypatch.setattr(chat_route.threading, "Thread", prohibido)
    handler = chat_route.ActividadHandler(job_id="sin-llm-auxiliar")
    handler.on_tool_start({"name": "consultar_drive"}, "privado", run_id=uuid4())
    assert handler.actividades[-1]["texto"] == "Consultando Drive"
    assert "privado" not in str(handler.actividades)
