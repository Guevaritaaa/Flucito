from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, LLMResult
from app.agents import traduccion_resumen as traductor
from app.api.v1.routes.chat import ActividadHandler
from app.core.config import settings
from uuid import uuid4


def test_solo_envia_resumen_y_preserva_historial(monkeypatch):
    llamadas = []
    class Modelo:
        def invoke(self, mensajes, config=None):
            llamadas.append((mensajes, config))
            return AIMessage(content="Voy a revisar la carpeta.")
    monkeypatch.setattr(settings, "groq_api_key", "falsa")
    monkeypatch.setattr(settings, "traducir_resumen_groq", True)
    monkeypatch.setattr(traductor, "crear_llm_groq", lambda **kwargs: Modelo())
    handler = ActividadHandler()
    id = uuid4()
    handler.on_chat_model_start({}, [], run_id=id)
    ai = AIMessage(content=[{"type":"reasoning", "summary":[{"type":"summary_text","text":"I will inspect the folder."}], "encrypted_content":"SECRETO"}])
    handler.on_llm_end(LLMResult(generations=[[ChatGeneration(message=ai)]]), run_id=id)
    assert handler.actividades[0]["resumen"] == "Voy a revisar la carpeta."
    assert handler.actividades[0]["resumen_idioma"] == "groq"
    assert len(llamadas) == 1 and llamadas[0][0][1].content == "I will inspect the folder."
    assert "SECRETO" not in str(llamadas)
    assert llamadas[0][1] == {"callbacks": []}


def test_error_o_resumen_excesivo_conserva_original(monkeypatch):
    class Modelo:
        def invoke(self, *args, **kwargs):
            raise RuntimeError("credencial o contenido privado")
    monkeypatch.setattr(settings, "groq_api_key", "falsa")
    monkeypatch.setattr(traductor, "crear_llm_groq", lambda **kwargs: Modelo())
    assert traductor.traducir_resumen("Original") == ("Original", "original")
    texto = "x" * (traductor.MAX_CARACTERES + 1)
    assert traductor.traducir_resumen(texto) == (texto, "original")
