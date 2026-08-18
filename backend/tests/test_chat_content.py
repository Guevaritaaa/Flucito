from langchain_core.messages import AIMessage

from app.api.v1.routes.chat import contenido_a_texto


def test_contenido_a_texto_normaliza_responses_api() -> None:
    mensaje = AIMessage(content=[{"type": "text", "text": "Respuesta Luna"}])

    assert contenido_a_texto(mensaje) == "Respuesta Luna"
