import json
from uuid import uuid4

from langchain_core.messages import AIMessage, AIMessageChunk
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, LLMResult
from app.api.v1.routes.chat import ActividadHandler
from app.schemas.chat import ActividadChat
from app.agents import llm_router


def test_eventos_observables_actualizan_sin_duplicarse():
    handler = ActividadHandler()
    for paso in ("buscar", "restaurar", "verificar"):
        for estado in ("en_curso", "completado", "completado"):
            handler.on_custom_event("flucito_paso", {"id": paso, "paso": paso, "estado": estado}, run_id=uuid4())
    assert len(handler.actividades) == 3
    assert [a["texto"] for a in handler.actividades] == ["Buscando la carpeta", "Restaurando la carpeta", "Verificando su ubicación"]
    assert all(a["estado"] == "completado" for a in handler.actividades)


def test_resumen_solo_del_modelo_se_agrega_y_finaliza_sin_filtrar_otros_bloques(monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "traducir_resumen_groq", False)
    handler = ActividadHandler()
    run_id = uuid4()
    handler.on_chat_model_start({}, [], run_id=run_id)
    for texto in ("Revisaré ", "la ubicación."):
        chunk = ChatGenerationChunk(message=AIMessageChunk(content=[{"type": "reasoning", "index": 0, "encrypted_content": "SECRETO", "summary": [{"type": "summary_text", "index": 0, "text": texto}]}]))
        handler.on_llm_new_token("", run_id=run_id, chunk=chunk)
    assert handler.actividades[0]["resumen"] == "Revisaré la ubicación."
    ai = AIMessage(content=[{"type": "reasoning", "encrypted_content": "SECRETO", "summary": [{"type": "summary_text", "text": "Ubicación revisada."}]}])
    handler.on_llm_end(LLMResult(generations=[[ChatGeneration(message=ai)]]), run_id=run_id)
    assert handler.actividades[0]["resumen"] == "Ubicación revisada."
    assert "SECRETO" not in json.dumps(handler.actividades)
    assert ActividadChat(**handler.actividades[0]).resumen == "Ubicación revisada."


def test_sin_resumen_no_inventa_razonamiento_y_no_declara_exito_parcial():
    handler = ActividadHandler()
    run_id = uuid4()
    handler.on_tool_start({"name": "gestionar_archivos_drive"}, "privado", run_id=run_id)
    handler.on_tool_end(json.dumps({"ok": False, "estado": "parcial"}), run_id=run_id)
    assert handler.actividades[0]["estado"] == "parcial"
    assert "resumen" not in handler.actividades[0]
    assert ActividadChat(texto="Historial anterior", estado="completado").resumen is None


def test_configuracion_luna6_responses_y_reversion(monkeypatch):
    from app.core.config import Settings
    assert Settings.model_fields["openai_model"].default == "gpt-6-luna"
    monkeypatch.setattr(llm_router.settings, "openai_api_key", "clave-falsa")
    monkeypatch.setattr(llm_router.settings, "openai_reasoning_effort", "medium")
    monkeypatch.setattr(llm_router.settings, "openai_reasoning_summary", True)
    modelo = llm_router.crear_llm_openai(responses=True)
    assert modelo.reasoning == {"effort": "medium", "summary": "auto"}
    assert "reasoning.encrypted_content" in modelo.include
    legado = llm_router.crear_llm_openai(responses=False)
    assert legado.reasoning_effort == "none"
    assert legado.reasoning is None
