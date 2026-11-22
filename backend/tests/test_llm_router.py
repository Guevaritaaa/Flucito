import json
import logging

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
import pytest

from app.agents import graph
from app.agents.graph import (
    MAX_ITERACIONES_TOOLS,
    contar_rondas_herramientas_turno_actual,
    es_error_reintentable,
    invocar_con_fallback,
    nodo_flucito,
)
from app.agents.llm_router import crear_llm_groq
from app.agents import llm_router
from app.core.config import Settings


@pytest.fixture(autouse=True)
def configurar_proveedores(monkeypatch):
    monkeypatch.setattr(llm_router.settings, "llm_primary_provider", "openai")
    monkeypatch.setattr(llm_router.settings, "groq_tpm_budget", 8000)
    monkeypatch.setattr(llm_router.settings, "groq_max_output_tokens", 1024)


def eventos_llm(caplog):
    return [json.loads(r.message) for r in caplog.records if r.name == llm_router.__name__]


class ErrorConEstado(Exception):
    status_code = 429


class ModeloFalso:
    def __init__(self, respuesta=None, error=None):
        self.respuesta = respuesta
        self.error = error
        self.llamadas = 0

    def invoke(self, mensajes):
        self.llamadas += 1
        if self.error:
            raise self.error
        return self.respuesta


def test_fallback_se_usa_ante_limite_del_proveedor() -> None:
    primario = ModeloFalso(error=ErrorConEstado("límite"))
    respaldo = ModeloFalso(respuesta="respuesta OpenAI")

    respuesta = invocar_con_fallback(["mensaje"], primario, respaldo)

    assert respuesta == "respuesta OpenAI"
    assert primario.llamadas == 1
    assert respaldo.llamadas == 1


def test_error_no_reintentable_se_propaga() -> None:
    error = ValueError("entrada inválida")
    primario = ModeloFalso(error=error)
    respaldo = ModeloFalso(respuesta="no debe ejecutarse")

    with pytest.raises(ValueError, match="entrada inválida"):
        invocar_con_fallback(["mensaje"], primario, respaldo)

    assert respaldo.llamadas == 0


def test_reconoce_modelo_no_disponible() -> None:
    assert es_error_reintentable(Exception("model_not_found"))


def test_reconoce_error_tool_use_failed_de_groq() -> None:
    class ErrorBadRequest(Exception):
        status_code = 400

    assert es_error_reintentable(ErrorBadRequest("tool_use_failed: failed_generation"))

    primario = ModeloFalso(error=ErrorBadRequest("tool_use_failed"))
    respaldo = ModeloFalso(respuesta="respuesta respaldo")
    assert invocar_con_fallback(["mensaje"], primario, respaldo) == "respuesta respaldo"
    assert primario.llamadas == 1
    assert respaldo.llamadas == 1


def test_temperatura_baja_para_precision_en_herramientas() -> None:
    modelo = crear_llm_groq()
    assert getattr(modelo, "temperature", None) == 0.1


def test_limite_de_iteraciones_corta_bucle_de_herramientas(monkeypatch) -> None:
    modelo_con_tools = ModeloFalso(respuesta=AIMessage(content="con tools"))
    modelo_sin_tools = ModeloFalso(respuesta=AIMessage(content="respuesta final sintetizada"))

    monkeypatch.setattr(graph, "llm_primario_con_herramientas", modelo_con_tools)
    monkeypatch.setattr(graph, "llm_respaldo_con_herramientas", None)
    monkeypatch.setattr(graph, "llm_primario", modelo_sin_tools)
    monkeypatch.setattr(graph, "llm_respaldo", None)

    mensajes_turno = [HumanMessage(content="Revisa y ordena todo")]
    for i in range(MAX_ITERACIONES_TOOLS):
        mensajes_turno.append(
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "consultar_drive",
                        "args": {"modo_consulta": "explorar_estructura"},
                        "id": f"call_{i}",
                    }
                ],
            )
        )
        mensajes_turno.append(
            ToolMessage(content='{"ok": true}', tool_call_id=f"call_{i}")
        )

    assert contar_rondas_herramientas_turno_actual(mensajes_turno) == MAX_ITERACIONES_TOOLS

    resultado = nodo_flucito({"messages": mensajes_turno})
    assert resultado["messages"][-1].content == "respuesta final sintetizada"
    assert modelo_con_tools.llamadas == 0
    assert modelo_sin_tools.llamadas == 1


def test_configuracion_predeterminada_conserva_luna():
    configuracion = Settings(_env_file=None, llm_primary_provider="openai")
    assert Settings.model_fields["llm_primary_provider"].default == "openai"
    assert configuracion.openai_model == "gpt-5.6-luna"
    assert configuracion.groq_tpm_budget == 8000
    with pytest.raises(ValueError):
        Settings(_env_file=None, groq_tpm_budget=0)
    with pytest.raises(ValueError):
        Settings(_env_file=None, llm_primary_provider="inexistente")


def test_consulta_normal_solo_usa_openai_y_registra_sin_contenido(caplog):
    caplog.set_level(logging.INFO, logger=llm_router.__name__)
    primario = ModeloFalso(respuesta="Luna")
    respaldo = ModeloFalso(respuesta="Groq")
    assert invocar_con_fallback([HumanMessage(content="SECRETO_USUARIO")], primario, respaldo) == "Luna"
    assert primario.llamadas == 1
    assert respaldo.llamadas == 0
    evento, = eventos_llm(caplog)
    assert evento["provider"] == "openai"
    assert evento["model"] == "gpt-5.6-luna"
    assert evento["result"] == "success"
    assert evento["duration_ms"] >= 0
    assert evento["request_id"]
    assert evento["fallback_reason"] is None
    assert "SECRETO_USUARIO" not in caplog.text


def test_respaldo_pequeno_comparte_id_y_registra_motivo(caplog):
    caplog.set_level(logging.INFO, logger=llm_router.__name__)
    primario = ModeloFalso(error=ErrorConEstado("CLAVE_PRIVADA_EN_ERROR"))
    respaldo = ModeloFalso(respuesta="Groq")
    assert invocar_con_fallback(["Hola"], primario, respaldo) == "Groq"
    primero, segundo = eventos_llm(caplog)
    assert primero["request_id"] == segundo["request_id"]
    assert primero["result"] == "error"
    assert segundo["provider"] == "groq"
    assert segundo["fallback_reason"] == "primary_http_429"
    assert segundo["estimated_tokens"] <= 8000
    assert "CLAVE_PRIVADA_EN_ERROR" not in caplog.text


def test_incidente_11273_tokens_omite_groq(monkeypatch, caplog):
    # Reproduce el tamano reportado; no se dispone del contenido del incidente.
    caplog.set_level(logging.INFO, logger=llm_router.__name__)
    monkeypatch.setattr(llm_router, "estimar_tokens_carga", lambda mensajes, modelo: 11273)
    error = ErrorConEstado("fallo recuperable")
    primario = ModeloFalso(error=error)
    respaldo = ModeloFalso(respuesta="no enviar")
    with pytest.raises(ErrorConEstado) as resultado:
        invocar_con_fallback(["incidente"], primario, respaldo)
    assert resultado.value is error
    assert respaldo.llamadas == 0
    evento = eventos_llm(caplog)[-1]
    assert evento["result"] == "skipped"
    assert evento["fallback_reason"] == "groq_token_budget_exceeded"
    assert evento["estimated_tokens"] == 11273 + 1024


def test_estimacion_incluye_sistema_historial_tools_y_esquemas():
    modelo = ModeloFalso()
    mensajes = [SystemMessage(content="sistema"), HumanMessage(content="hola")]
    minimo = llm_router.estimar_tokens_carga(mensajes, modelo)
    modelo.kwargs = {"tools": [{"type": "function", "function": {"name": "consulta", "description": "x" * 30000}}]}
    assert llm_router.estimar_tokens_carga(mensajes, modelo) > minimo + 8000
    modelo.kwargs = {}
    mensajes += [AIMessage(content="", tool_calls=[{"name": "consulta", "id": "call_1", "args": {"dato": "x" * 3000}}]), ToolMessage(content="x" * 3000, tool_call_id="call_1")]
    assert llm_router.estimar_tokens_carga(mensajes, modelo) > minimo + 2000


def test_esquemas_grandes_impiden_respaldo_real_sin_mock_estimador():
    respaldo = ModeloFalso(respuesta="no enviar")
    respaldo.kwargs = {"tools": [{"description": "x" * 30000}]}
    with pytest.raises(ErrorConEstado):
        invocar_con_fallback(["Hola"], ModeloFalso(error=ErrorConEstado()), respaldo)
    assert respaldo.llamadas == 0


@pytest.mark.parametrize("con_respaldo", [True, False])
def test_413_no_se_reenvia(con_respaldo, caplog):
    caplog.set_level(logging.INFO, logger=llm_router.__name__)
    error = ErrorConEstado("carga rechazada")
    error.status_code = 413
    primario = ModeloFalso(error=error)
    respaldo = ModeloFalso() if con_respaldo else None
    assert not es_error_reintentable(error)
    with pytest.raises(ErrorConEstado):
        invocar_con_fallback(["Hola"], primario, respaldo)
    assert primario.llamadas == 1
    assert respaldo is None or respaldo.llamadas == 0
    assert eventos_llm(caplog)[-1]["fallback_reason"] == "http_413_payload_rejected"


def test_413_del_respaldo_tampoco_se_reintenta():
    error = ErrorConEstado("carga rechazada")
    error.status_code = 413
    respaldo = ModeloFalso(error=error)
    with pytest.raises(ErrorConEstado) as resultado:
        invocar_con_fallback(["Hola"], ModeloFalso(error=ErrorConEstado()), respaldo)
    assert resultado.value is error
    assert respaldo.llamadas == 1


def test_estimacion_invalida_omite_respaldo(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=llm_router.__name__)
    def fallar(*args):
        raise TypeError("dato no serializable")
    monkeypatch.setattr(llm_router, "estimar_tokens_carga", fallar)
    respaldo = ModeloFalso()
    with pytest.raises(ErrorConEstado):
        invocar_con_fallback(["hola"], ModeloFalso(error=ErrorConEstado()), respaldo)
    assert respaldo.llamadas == 0
    assert eventos_llm(caplog)[-1]["fallback_reason"] == "token_estimation_failed"


def test_error_sin_respaldo_reintenta_una_sola_vez(caplog):
    caplog.set_level(logging.INFO, logger=llm_router.__name__)
    primario = ModeloFalso(error=ErrorConEstado())
    with pytest.raises(ErrorConEstado):
        invocar_con_fallback(["hola"], primario, None)
    assert primario.llamadas == 2
    assert len(eventos_llm(caplog)) == 2


def test_creacion_openai_sin_clave_groq(monkeypatch):
    monkeypatch.setattr(llm_router.settings, "groq_api_key", None)
    monkeypatch.setattr(llm_router.settings, "openai_api_key", "clave-falsa")
    primario, respaldo = llm_router.crear_llms()
    assert primario.model_name == "gpt-5.6-luna"
    assert primario.max_retries == 0
    assert respaldo is None


def test_groq_limita_salida_y_desactiva_reintentos():
    modelo = crear_llm_groq()
    assert modelo.max_tokens == 1024
    assert modelo.max_retries == 0
