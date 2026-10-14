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

