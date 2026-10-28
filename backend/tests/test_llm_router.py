from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
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
