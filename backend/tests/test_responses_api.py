import json

import httpx
import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage, AIMessageChunk
from langchain_core.tools import tool
from langchain_core.outputs import LLMResult, ChatGeneration
from langchain_openai import ChatOpenAI

from app.agents import graph, llm_router
from app.agents.ejecucion_tools import ejecutar_herramientas
from app.agents.seleccion_tools import seleccionar_herramientas, enlazar_herramientas
from app.agents.tools import HERRAMIENTAS
from app.api.v1.routes import chat


def respuesta(output, id="resp_1"):
    return {"id": id, "object": "response", "created_at": 1, "status": "completed", "model": "gpt-5.6-luna",
            "output": output, "usage": {"input_tokens": 20, "output_tokens": 10, "total_tokens": 30,
                                       "input_tokens_details": {"cached_tokens": 0}, "output_tokens_details": {"reasoning_tokens": 0}}}


def texto(valor):
    return {"type": "message", "id": "msg_1", "status": "completed", "role": "assistant",
            "content": [{"type": "output_text", "text": valor, "annotations": []}]}


def modelo_mock(handler):
    return ChatOpenAI(model="gpt-5.6-luna", api_key="clave-de-prueba", use_responses_api=True,
                      output_version="responses/v1", store=False, use_previous_response_id=False,
                      max_retries=0, http_client=httpx.Client(transport=httpx.MockTransport(handler)))


def test_interruptor_es_reversible_y_conserva_modelo(monkeypatch):
    monkeypatch.setattr(llm_router.settings, "openai_api_key", "clave-de-prueba")
    for flag in (False, True):
        monkeypatch.setattr(llm_router.settings, "openai_use_responses_api", flag)
        modelo = llm_router.crear_llm_openai()
        assert modelo.use_responses_api is flag
        assert modelo.model_name == "gpt-5.6-luna"
        assert modelo.output_version == ("responses/v1" if flag else "v0")
        assert modelo.store is False
        assert modelo.use_previous_response_id is False
    assert llm_router.crear_llm_openai("gpt-6-luna", True).model_name == "gpt-6-luna"


def test_sdk_responses_conserva_call_id_hasta_el_resultado():
    peticiones = []
    @tool
    def leer(dato: str) -> str:
        """Consulta un dato de prueba."""
        return dato.upper()
    def handler(request):
        carga = json.loads(request.content)
        peticiones.append(carga)
        assert request.url.path == "/v1/responses"
        if len(peticiones) == 1:
            return httpx.Response(200, json=respuesta([{"type": "function_call", "id": "fc_item", "call_id": "call_real", "name": "leer", "arguments": '{"dato":"hola"}', "status": "completed"}]))
        return httpx.Response(200, json=respuesta([texto("HOLA")], "resp_2"))
    modelo = enlazar_herramientas(modelo_mock(handler), [leer])
    historial = [HumanMessage(content="consulta hola")]
    primero = modelo.invoke(historial)
    assert primero.tool_calls[0]["id"] == "call_real"
    resultado = ejecutar_herramientas({"messages": [*historial, primero]}, [leer])["messages"]
    assert resultado[0].tool_call_id == "call_real"
    final = modelo.invoke([*historial, primero, *resultado])
    assert final.text == "HOLA"
    assert peticiones[0]["parallel_tool_calls"] is False
    assert peticiones[0]["store"] is False
    assert "previous_response_id" not in peticiones[1]
    assert peticiones[0]["tools"][0]["name"] == "leer"
    assert any(i.get("type") == "function_call_output" and i["call_id"] == "call_real" and i["output"] == "HOLA" for i in peticiones[1]["input"])


@pytest.mark.parametrize("consulta,reducida", [
    ("¿Qué factores de precio tengo?", True), ("Muéstrame los factores actuales", True),
    ("Consulta los factores y genera reportes", False), ("Factores y carpetas en Drive", False),
    ("Cambia los factores de FESTO", False), ("Genera el reporte", False),
    ("¿Cuáles son los factores? Después restaura 17-11-2026", False),
])
def test_reduccion_conservadora(consulta, reducida):
    seleccion = seleccionar_herramientas([HumanMessage(content=consulta)], HERRAMIENTAS)
    assert len(seleccion) == (1 if reducida else 6)
    if reducida:
        assert seleccion[0].name == "consultar_almacen"


def test_contexto_mixto_y_multimodal_no_pierden_herramientas():
    consulta = HumanMessage(content="Qué factores de precio tengo")
    ai = AIMessage(content="", tool_calls=[{"id": "c1", "name": "consultar_drive", "args": {}}])
    assert len(seleccionar_herramientas([consulta, ai], HERRAMIENTAS)) == 6
    assert len(seleccionar_herramientas([HumanMessage(content=[{"type": "text", "text": "Factores"}])], HERRAMIENTAS)) == 6


def test_lote_se_valida_completo_y_es_secuencial():
    ejecuciones = []
    @tool
    def escribir(valor: int) -> str:
        """Guarda un valor en memoria de prueba."""
        ejecuciones.append(valor)
        return json.dumps({"ok": True, "valores": list(ejecuciones)})
    llamadas = [{"id": "a", "name": "escribir", "args": {"valor": 1}}, {"id": "b", "name": "escribir", "args": {"valor": 2}}]
    resultado = ejecutar_herramientas({"messages": [AIMessage(content="", tool_calls=llamadas)]}, [escribir])
    assert ejecuciones == [1, 2]
    assert [m.tool_call_id for m in resultado["messages"]] == ["a", "b"]
    assert json.loads(resultado["messages"][1].content)["valores"] == [1, 2]
    ejecuciones.clear()
    llamadas[1]["args"] = {"valor": "SECRETO"}
    resultado = ejecutar_herramientas({"messages": [AIMessage(content="", tool_calls=llamadas)]}, [escribir])
    assert ejecuciones == []
    assert all(m.status == "error" for m in resultado["messages"])
    assert "SECRETO" not in str(resultado)


@pytest.mark.parametrize("fallo", ["error", "confirmacion", "excepcion"])
def test_no_continua_escrituras_tras_fallo_o_confirmacion(fallo):
    ejecutadas = []
    @tool
    def accion(valor: int) -> str:
        """Escritura de prueba."""
        ejecutadas.append(valor)
        if fallo == "excepcion":
            raise RuntimeError("SECRETO")
        return json.dumps({"ok": fallo != "error", "requiere_confirmacion": fallo == "confirmacion"})
    llamadas = [{"id": str(i), "name": "accion", "args": {"valor": i}} for i in (1, 2)]
    resultado = ejecutar_herramientas({"messages": [AIMessage(content="", tool_calls=llamadas)]}, [accion])
    assert ejecutadas == [1]
    assert resultado["messages"][1].status == "error"
    assert "SECRETO" not in str(resultado)


def test_ids_repetidos_y_extras_no_se_ejecutan():
    ejecutadas = []
    @tool
    def accion(valor: int) -> str:
        """Escritura de prueba."""
        ejecutadas.append(valor)
        return "ok"
    llamada = {"id": "repetido", "name": "accion", "args": {"valor": 1}}
    with pytest.raises(ValueError):
        ejecutar_herramientas({"messages": [AIMessage(content="", tool_calls=[llamada, llamada])]}, [accion])
    with pytest.raises(ValueError):
        ejecutar_herramientas({"messages": [ToolMessage(content="previo", tool_call_id="repetido"), AIMessage(content="", tool_calls=[llamada])]}, [accion])
    llamada["args"]["extra"] = True
    salida = ejecutar_herramientas({"messages": [AIMessage(content="", tool_calls=[llamada])]}, [accion])
    assert salida["messages"][0].status == "error"
    assert ejecutadas == []


def test_fallback_no_envia_bloques_responses_a_groq():
    mensaje = AIMessage(content=[{"type": "reasoning", "summary": [{"type": "summary_text", "text": "privado"}]},
                                 {"type": "text", "text": "Texto público"},
                                 {"type": "function_call", "id": "fc_1", "call_id": "c1", "name": "leer", "arguments": "{}"}],
                        tool_calls=[{"id": "c1", "name": "leer", "args": {}}])
    carga = llm_router.preparar_mensajes([mensaje], "groq", object())
    assert carga[0].content == "Texto público"
    assert carga[0].tool_calls[0]["id"] == "c1"
    assert isinstance(mensaje.content, list)


def test_cierre_del_job_iguala_texto_final_y_guardado(monkeypatch):
    guardadas = []
    class Grafo:
        def stream(self, estado, config, stream_mode):
            yield "values", {"messages": [*estado["messages"], AIMessage(content=[{"type": "reasoning", "summary": []}, {"type": "text", "text": "Resultado final"}])]}
    monkeypatch.setattr(chat, "grafo", Grafo())
    monkeypatch.setattr(chat, "_obtener_mensajes_previos_bd", lambda *a: [])
    monkeypatch.setattr(chat, "_guardar_interaccion_en_bd", lambda **kw: guardadas.append(kw["respuesta_chat"].respuesta))
    job_id = "responses-final"
    chat._JOBS[job_id] = {"status": "running", "texto_provisional": "Texto previo", "usuario_id": None}
    try:
        chat._trabajador_chat(job_id, chat.ChatRequest(mensaje="Hola", session_id="prueba"))
        job = chat._JOBS[job_id]
        assert job["status"] == "completed"
        assert job["texto_provisional"] == job["result"].respuesta == guardadas[0] == "Resultado final"
    finally:
        chat._JOBS.pop(job_id, None)
        chat._CONTEXTO_JOB.job_id = None


def test_sdk_streaming_real_con_langgraph_conserva_texto(monkeypatch):
    def handler(request):
        assert json.loads(request.content)["stream"] is True
        item = texto("Hola mundo")
        eventos = [
            {"type": "response.created", "response": respuesta([], "resp_stream")},
            {"type": "response.output_item.added", "output_index": 0, "item": {**item, "content": []}},
            {"type": "response.content_part.added", "item_id": "msg_1", "output_index": 0, "content_index": 0, "part": {"type": "output_text", "text": "", "annotations": []}},
            *[{"type": "response.output_text.delta", "item_id": "msg_1", "output_index": 0, "content_index": 0, "delta": t} for t in ("Hola ", "mundo")],
            {"type": "response.output_text.done", "item_id": "msg_1", "output_index": 0, "content_index": 0, "text": "Hola mundo"},
            {"type": "response.output_item.done", "output_index": 0, "item": item},
            {"type": "response.completed", "response": respuesta([item], "resp_stream")},
        ]
        body = "".join(f"event: {e['type']}\ndata: {json.dumps(e)}\n\n" for e in eventos)
        return httpx.Response(200, headers={"Content-Type": "text/event-stream"}, text=body)
    modelo = modelo_mock(handler)
    monkeypatch.setattr(graph, "llm_primario_con_herramientas", modelo)
    monkeypatch.setattr(graph, "llm_respaldo_con_herramientas", None)
    monkeypatch.setattr(llm_router.settings, "llm_primary_provider", "openai")
    actividad = chat.ActividadHandler()
    eventos = list(graph.grafo.stream({"messages": [HumanMessage(content="Hola")]}, config={"configurable": {"thread_id": "test-stream-responses"}, "callbacks": [actividad]}, stream_mode=["messages", "values"]))
    final = [contenido for modo, contenido in eventos if modo == "values"][-1]
    assert final["messages"][-1].text == actividad.texto_provisional == "Hola mundo"


def test_razonamiento_y_llamadas_no_se_mezclan_con_respuesta():
    from langchain_core.outputs import ChatGenerationChunk
    from uuid import uuid4
    actividad = chat.ActividadHandler()
    run_id = uuid4()
    chunk = ChatGenerationChunk(message=AIMessageChunk(content=[{"type": "reasoning", "summary": [{"type": "summary_text", "text": "privado"}]}]))
    actividad.on_llm_new_token("privado", run_id=run_id, chunk=chunk)
    assert actividad.texto_provisional == ""
    rechazo = AIMessage(content=[{"type": "refusal", "refusal": "No puedo completar esa solicitud."}])
    assert chat.contenido_a_texto(rechazo) == "No puedo completar esa solicitud."


def test_adjuntos_de_salida_se_conservan_al_cerrar_stream_y_en_historial(monkeypatch):
    import asyncio
    guardadas = []
    datos = {"ok": True, "tipo": "busqueda_historica", "reportes": [{"id": "excel-fixture", "nombre": "ENTRADAS_ALMACEN_17-11-2026.xlsx", "fecha": "17-11-2026"}]}
    class Grafo:
        def stream(self, estado, config, stream_mode):
            yield "values", {"messages": [*estado["messages"], ToolMessage(content=json.dumps(datos), tool_call_id="c1"), AIMessage(content=[{"type": "text", "text": "Reporte del 17-11-2026 listo."}])]}
    monkeypatch.setattr(chat, "grafo", Grafo())
    monkeypatch.setattr(chat, "_obtener_mensajes_previos_bd", lambda *a: [])
    monkeypatch.setattr(chat, "_guardar_interaccion_en_bd", lambda **kw: guardadas.append(kw["respuesta_chat"].model_dump()))
    job_id = "responses-adjuntos"
    chat._JOBS[job_id] = {"status": "running", "usuario_id": None, "error": None}
    try:
        chat._trabajador_chat(job_id, chat.ChatRequest(mensaje="Descarga el reporte de 17-11-2026", session_id="adjuntos"))
        async def leer():
            return [evento async for evento in chat.eventos_chat(job_id, None).body_iterator]
        evento = json.loads(asyncio.run(leer())[0][len("data: "):])
        assert evento["result"] == guardadas[0]
        assert evento["texto_provisional"] == guardadas[0]["respuesta"]
        assert "archivo_id=excel-fixture" in guardadas[0]["reportes_historicos"][0]["url"]
    finally:
        chat._JOBS.pop(job_id, None)
        chat._CONTEXTO_JOB.job_id = None


def test_pregunta_solo_factores_no_ejecuta_funcion_no_enlazada():
    ai = AIMessage(content="", tool_calls=[{"id": "no-permitida", "name": "gestionar_archivos_drive", "args": {"accion": "restablecer_carpeta", "ruta_origen": "17-11-2026"}}])
    resultado = graph.herramientas({"messages": [HumanMessage(content="Qué factores tengo"), ai]}, {})
    assert resultado["messages"][0].status == "error"


def test_comparador_mide_uso_y_costo_solo_con_tarifas_explicitas():
    from evaluations.comparar_responses import ejecutar_caso, resumen
    caso = {"id": "factores", "solicitud": "Qué factores tengo", "herramientas": [{"name": "consultar_almacen", "args": {"tipo_consulta": "catalogo_factores"}}], "texto_esperado": ["FESTO"]}
    uso = {"input_tokens": 100, "output_tokens": 20, "total_tokens": 120, "input_token_details": {"cache_read": 10}}
    class Modelo:
        def __init__(self):
            self.respuestas = [AIMessage(content="", tool_calls=[{"id": "factor1", "name": "consultar_almacen", "args": {"tipo_consulta": "catalogo_factores"}}], usage_metadata=uso), AIMessage(content="FESTO", usage_metadata=uso)]
        def bind_tools(self, tools, **kwargs):
            assert len(tools) == 1
            return self
        def invoke(self, mensajes):
            return self.respuestas.pop(0)
    fila = ejecutar_caso(caso, Modelo(), {"input_per_million": 1, "cached_input_per_million": .5, "output_per_million": 2})
    assert fila["completada"]
    assert fila["uso"]["input_tokens"] == 200
    assert fila["costo_usd"] == pytest.approx(.00027)
    assert resumen([fila])["costo_por_tarea_resuelta_usd"] == fila["costo_usd"]
    sin_tarifas = ejecutar_caso(caso, Modelo())
    assert sin_tarifas["completada"]
    assert sin_tarifas["costo_usd"] is None


def test_lote_con_funcion_desconocida_no_ejecuta_ni_la_primera():
    ejecutadas = []
    @tool
    def valida() -> str:
        """Consulta de prueba."""
        ejecutadas.append(True)
        return "ok"
    llamadas = [{"id": "v1", "name": "valida", "args": {}}, {"id": "v2", "name": "inventada", "args": {}}]
    salida = ejecutar_herramientas({"messages": [AIMessage(content="", tool_calls=llamadas)]}, [valida])
    assert all(m.status == "error" for m in salida["messages"])
    assert ejecutadas == []


def test_generacion_puntual_no_amplia_alcance_y_rechaza_homonimos():
    from app.services.almacen.fuentes.sincronizador import filtrar_carpeta_solicitada
    from app.services.almacen.fuentes.google_drive import CarpetaFactura
    uno = CarpetaFactura(id="uno", nombre="17-11-2026", archivos=())
    dos = CarpetaFactura(id="dos", nombre="18-11-2026", archivos=())
    assert filtrar_carpeta_solicitada([uno, dos], "2026-11-17") == [uno]
    assert filtrar_carpeta_solicitada([uno, dos], "id:dos") == [dos]
    with pytest.raises(ValueError):
        filtrar_carpeta_solicitada([uno, dos], "19-11-2026")
    with pytest.raises(ValueError):
        filtrar_carpeta_solicitada([uno, uno], "17-11-2026")


def test_fecha_se_conserva_entre_confirmaciones(monkeypatch, tmp_path):
    from app.agents.tools import almacen_tools
    monkeypatch.setattr(almacen_tools, "_obtener_carpeta_datos", lambda: tmp_path)
    monkeypatch.setattr(almacen_tools.settings, "google_drive_folder_id", "root")
    monkeypatch.setattr(almacen_tools.settings, "google_oauth_client_file", "credencial-falsa")
    recibidas = []
    def sincronizar(**kwargs):
        recibidas.append(kwargs)
        return {"requiere_confirmacion": True, "tipo_confirmacion": "solo_xml", "pregunta_usuario": "¿Continuar?", "carpetas_solo_xml": ["17-11-2026"]}
    monkeypatch.setattr(almacen_tools, "sincronizar_drive", sincronizar)
    almacen_tools.generar_entradas_almacen.invoke({"carpeta_especifica": "17-11-2026"})
    almacen_tools.generar_entradas_almacen.invoke({"confirmar_solo_xml": True})
    assert [r["carpeta_especifica"] for r in recibidas] == ["17-11-2026", "17-11-2026"]


def test_argumentos_normalizados_coinciden_con_bloque_responses(monkeypatch):
    llamada = {"id": "normalizada", "name": "consultar_drive", "args": {"modo_consulta": "explorar_estructura", "ubicacion": "raiz"}}
    ai = AIMessage(content=[{"type": "function_call", "id": "fc_normalizada", "call_id": "normalizada", "name": "consultar_drive", "arguments": json.dumps(llamada["args"])}], tool_calls=[llamada])
    monkeypatch.setattr(graph, "invocar_con_fallback", lambda *a: ai)
    final = graph.nodo_flucito({"messages": [HumanMessage(content="¿Qué carpetas hay?")]})["messages"][0]
    assert final.tool_calls[0]["args"]["ubicacion"] == "todas"
    assert json.loads(final.content[0]["arguments"]) == final.tool_calls[0]["args"]
