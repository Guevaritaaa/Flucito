import pytest

from app.agents.graph import es_error_reintentable, invocar_con_fallback


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
