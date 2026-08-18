"""Construcción centralizada de los modelos usados por Flucito."""

from langchain_core.language_models import BaseChatModel
from langchain_groq import ChatGroq
from langchain_openai import ChatOpenAI

from app.core.config import settings


def crear_llm_groq() -> BaseChatModel:
    """Crea el modelo primario de Groq."""
    return ChatGroq(
        model=settings.groq_model,
        api_key=settings.groq_api_key,
        temperature=0.4,
    )


def crear_llm_openai() -> BaseChatModel:
    """Crea el modelo de respaldo de OpenAI."""
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY no está configurada")

    return ChatOpenAI(
        model=settings.openai_model,
        api_key=settings.openai_api_key,
        temperature=0.4,
        use_responses_api=True,
    )


def crear_llms() -> tuple[BaseChatModel, BaseChatModel | None]:
    """Devuelve modelo primario y fallback sin ejecutar llamadas externas."""
    if settings.llm_primary_provider.lower() == "openai":
        primario = crear_llm_openai()
        respaldo = crear_llm_groq() if settings.llm_fallback_enabled else None
    else:
        primario = crear_llm_groq()
        respaldo = (
            crear_llm_openai()
            if settings.llm_fallback_enabled and settings.openai_api_key
            else None
        )

    return primario, respaldo
