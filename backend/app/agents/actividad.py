"""Eventos observables; nunca generan etiquetas con otra llamada al modelo."""

from langchain_core.callbacks.manager import dispatch_custom_event
from langchain_core.runnables.config import ensure_config

PASOS = {"buscar": "Buscando la carpeta", "restaurar": "Restaurando la carpeta", "verificar": "Verificando su ubicación"}
ESTADOS = {"en_curso", "completado", "error", "parcial", "pendiente_verificar"}


def emitir_paso(id, paso, estado):
    if paso not in PASOS or estado not in ESTADOS:
        raise ValueError("Evento de actividad desconocido")
    config = ensure_config()
    if config.get("callbacks"):
        dispatch_custom_event("flucito_paso", {"id": id, "paso": paso, "estado": estado}, config=config)
