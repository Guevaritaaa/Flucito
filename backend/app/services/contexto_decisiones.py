"""Contexto por ejecución: nunca comparte confirmaciones entre conversaciones."""
from contextvars import ContextVar

contexto: ContextVar[dict | None] = ContextVar("decisiones_flucito", default=None)
