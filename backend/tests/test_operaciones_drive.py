import json
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from contextlib import contextmanager
from langchain_core.runnables.config import var_child_runnable_config

from app.services.almacen.fuentes import operaciones_drive as diario
from app.services.almacen.fuentes import navegador_drive as navegador
from app.services.almacen.fuentes import google_drive_client as drive


MIME = drive.MIME_CARPETA


@contextmanager
def set_config_context(config):
    token = var_child_runnable_config.set(config)
    try:
        yield
    finally:
        var_child_runnable_config.reset(token)


class Cliente:
    def __init__(self, modo="normal"):
        self.modo = modo
        self.escrituras = 0
        self.elementos = {
            "carpeta": {"id": "carpeta", "name": "17-11-2026", "mimeType": MIME, "parents": ["historico"]},
            "entradas": {"id": "entradas", "name": "ENTRADAS AL INVENTARIO", "mimeType": MIME, "parents": ["root"]},
        }

    def files(self):
        return self

    def get(self, fileId, **kwargs):
        def ejecutar(**kwargs):
            if self.modo == "sin_verificacion" and self.escrituras:
                raise ConnectionError("desconectado")
            return dict(self.elementos[fileId])
        return SimpleNamespace(execute=ejecutar)

    def update(self, fileId, addParents, **kwargs):
        def ejecutar(num_retries):
            assert num_retries == 0
            self.escrituras += 1
            if self.modo == "denegado":
                error = RuntimeError("acceso denegado")
                error.resp = SimpleNamespace(status=403)
                raise error
            if self.modo != "incierto_sin_cambio":
                self.elementos[fileId]["parents"] = [addParents]
            if self.modo in {"respuesta_perdida", "incierto_sin_cambio"}:
                raise ConnectionError("respuesta perdida")
            return {}
        return SimpleNamespace(execute=ejecutar)


@pytest.fixture(autouse=True)
def base_aislada(monkeypatch, tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'operaciones.db'}")
    monkeypatch.setattr(diario, "engine", engine)
    yield
    engine.dispose()


def test_respuesta_perdida_se_verifica_sin_repetir():
    cliente = Cliente("respuesta_perdida")
    with set_config_context({"configurable": {"drive_request_id": "solicitud"}}):
        op = diario.mover_verificado(cliente, "carpeta", "entradas", "historico")
    assert op["estado"] == "confirmada"
    assert diario.resultados("solicitud")[0]["padres_verificados"] == ["entradas"]
    diario.mover_verificado(cliente, "carpeta", "entradas")
    assert cliente.escrituras == 1


def test_desconexion_al_verificar_se_recupera_solo_con_lectura(monkeypatch):
    cliente = Cliente("sin_verificacion")
    with set_config_context({"configurable": {"drive_request_id": "solicitud"}}):
        with pytest.raises(RuntimeError, match="Pendiente"):
            diario.mover_verificado(cliente, "carpeta", "entradas", "historico")
    assert diario.resultados("solicitud")[0]["estado"] == "pendiente_verificar"
    cliente.modo = "normal"
    monkeypatch.setattr(drive, "crear_cliente_drive", lambda: cliente)
    assert "Movimiento confirmado" in diario.recuperar("solicitud")
    assert cliente.escrituras == 1


def test_pendiente_en_origen_no_reenvia_escritura():
    cliente = Cliente("incierto_sin_cambio")
    for _ in range(2):
        with pytest.raises(RuntimeError, match="Pendiente"):
            diario.mover_verificado(cliente, "carpeta", "entradas", "historico")
    assert cliente.escrituras == 1


def test_denegado_queda_fallido():
    cliente = Cliente("denegado")
    with set_config_context({"configurable": {"drive_request_id": "solicitud"}}):
        with pytest.raises(RuntimeError, match="fallido"):
            diario.mover_verificado(cliente, "carpeta", "entradas", "historico")
    assert diario.resultados("solicitud")[0]["estado"] == "fallida"
    assert cliente.elementos["carpeta"]["parents"] == ["historico"]


def test_no_mueve_si_falla_guardado_o_cambia_origen(monkeypatch):
    cliente = Cliente()
    with pytest.raises(ValueError, match="inicial"):
        diario.mover_verificado(cliente, "carpeta", "entradas", "otro")
    def fallar(*args):
        raise OSError("base no disponible")
    monkeypatch.setattr(diario, "guardar", fallar)
    with pytest.raises(OSError):
        diario.mover_verificado(cliente, "carpeta", "entradas", "historico")
    assert cliente.escrituras == 0


def test_ambigua_no_mueve_y_permite_elegir_id(monkeypatch):
    estructura = {
        "root": [{"id": "a", "name": "A", "mimeType": MIME}, {"id": "b", "name": "B", "mimeType": MIME}],
        "a": [{"id": "uno", "name": "17-11-2026", "mimeType": MIME}],
        "b": [{"id": "dos", "name": "17-11-2026", "mimeType": MIME}],
    }
    monkeypatch.setattr(navegador, "_listar_hijos", lambda cliente, padre: estructura.get(padre, []))
    resultado = navegador.mover_elemento_por_ruta("17-11-2026", "A", cliente=object(), carpeta_raiz_id="root")
    assert resultado["requiere_confirmacion"]
    assert {c["id"] for c in resultado["candidatos"]} == {"uno", "dos"}
    assert navegador.resolver_para_movimiento(object(), "id:dos", "root")["padre_id"] == "b"


def test_fallo_al_redactar_chat_conserva_movimiento_y_destino(monkeypatch):
    from app.api.v1.routes import chat
    from app.schemas.chat import ChatRequest
    cliente = Cliente()
    llamadas = []
    class Grafo:
        def invoke(self, estado, config):
            llamadas.append(config)
            with set_config_context(config):
                diario.mover_verificado(cliente, "carpeta", "entradas", "historico")
            raise ConnectionError("fallo al redactar")
    monkeypatch.setattr(chat, "grafo", Grafo())
    monkeypatch.setattr(chat, "_obtener_mensajes_previos_bd", lambda *a: [])
    monkeypatch.setattr(chat, "_guardar_interaccion_en_bd", lambda **kw: None)
    respuesta = chat._ejecutar_chat(ChatRequest(mensaje="restablece la carpeta 17-11-2026", session_id="prueba"))
    assert "Movimiento confirmado" in respuesta.respuesta
    assert "ENTRADAS AL INVENTARIO" in respuesta.respuesta
    assert cliente.escrituras == 1
    assert len(llamadas) == 1


def test_limite_rondas_usa_diario_sin_modelo(monkeypatch):
    from app.agents import graph
    from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
    config = {"configurable": {"drive_request_id": "limite"}}
    with set_config_context(config):
        diario.mover_verificado(Cliente(), "carpeta", "entradas", "historico")
    def prohibido(*args):
        raise AssertionError("No debe redactar de nuevo")
    monkeypatch.setattr(graph, "invocar_con_fallback", prohibido)
    mensajes = [HumanMessage(content="restablece")]
    for i in range(graph.MAX_ITERACIONES_TOOLS):
        mensajes += [AIMessage(content="", tool_calls=[{"name": "consulta", "id": str(i), "args": {}}]), ToolMessage(content="ok", tool_call_id=str(i))]
    assert "Movimiento confirmado" in graph.nodo_flucito({"messages": mensajes}, config)["messages"][0].content


def test_resultado_parcial_y_diario_durable():
    from sqlalchemy import create_engine
    with set_config_context({"configurable": {"drive_request_id": "parcial"}}):
        diario.mover_verificado(Cliente(), "carpeta", "entradas", "historico")
        with pytest.raises(RuntimeError):
            diario.mover_verificado(Cliente("denegado"), "carpeta", "entradas", "historico")
    url = diario.engine.url
    diario.engine.dispose()
    diario.engine = create_engine(url)
    assert "Resultado parcial" in diario.resumen(diario.resultados("parcial"))
    diario.engine.dispose()


def test_configuracion_real_de_herramienta_se_conserva(monkeypatch):
    from app.agents.tools.drive_tools import gestionar_archivos_drive
    from app.agents.tools import drive_tools
    cliente = Cliente()
    def mover(**kwargs):
        return diario.mover_verificado(cliente, "carpeta", "entradas", "historico")
    monkeypatch.setattr(drive_tools, "mover_elemento_por_ruta", mover)
    gestionar_archivos_drive.invoke(
        {"accion": "mover_elemento", "ruta_origen": "17-11-2026", "ruta_destino": "ENTRADAS AL INVENTARIO"},
        config={"configurable": {"drive_request_id": "real"}},
    )
    assert diario.resultados("real")[0]["estado"] == "confirmada"


def test_movimiento_explicito_completo_por_herramienta(monkeypatch):
    from app.agents.tools.drive_tools import gestionar_archivos_drive
    cliente = Cliente()
    cliente.elementos["historico"] = {"id": "historico", "name": "DOCUMENTOS ENTRADA", "mimeType": MIME, "parents": ["root"]}
    monkeypatch.setattr(navegador.settings, "google_drive_folder_id", "root")
    monkeypatch.setattr(navegador, "crear_cliente_drive", lambda: cliente)
    monkeypatch.setattr(navegador, "_listar_hijos", lambda c, padre: [dict(item) for item in cliente.elementos.values() if padre in item.get("parents", [])])
    config = {"configurable": {"drive_request_id": "integracion"}}
    primero = json.loads(gestionar_archivos_drive.invoke({"accion": "mover_elemento", "ruta_origen": "17-11-2026", "ruta_destino": "ENTRADAS AL INVENTARIO"}, config=config))
    segundo = json.loads(gestionar_archivos_drive.invoke({"accion": "mover_elemento", "ruta_origen": "id:carpeta", "ruta_destino": "ENTRADAS AL INVENTARIO"}, config=config))
    assert primero["estado"] == "confirmada"
    assert primero["nueva_ruta"] == "ENTRADAS AL INVENTARIO/17-11-2026"
    assert segundo["movido"] is False
    assert cliente.escrituras == 1
    assert len(diario.resultados("integracion")) == 2
