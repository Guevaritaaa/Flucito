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
    monkeypatch.setattr(chat_route.ActividadHandler, "_generar_resumen", lambda *args: None)
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


def test_resumen_usa_solo_descripcion_publica(monkeypatch) -> None:
    from uuid import uuid4
    from app.agents import graph

    llamadas = []

    class Modelo:
        def invoke(self, mensajes):
            llamadas.extend(mensajes)
            return AIMessage(content="Revisando archivos de Drive")

    monkeypatch.setattr(graph, "llm_primario", Modelo())
    handler = chat_route.ActividadHandler()
    run_id = str(uuid4())
    handler._iniciar(run_id, "Consultando Drive", "trabajando", "consultar_drive")
    handler._generar_resumen(run_id, "consultar_drive")
    assert handler.actividades[0]["texto"] == "Revisando archivos de Drive"
    assert llamadas[-1].content == "Consultando Drive"
