"""Reducción conservadora: solo preguntas inequívocas sobre el catálogo de factores."""

import re
import unicodedata

from langchain_openai import ChatOpenAI


def seleccionar_herramientas(mensajes, herramientas):
    ultimo = next((i for i in range(len(mensajes) - 1, -1, -1) if getattr(mensajes[i], "type", None) == "human"), None)
    if ultimo is None or not isinstance(mensajes[ultimo].content, str):
        return herramientas
    consulta = unicodedata.normalize("NFKD", mensajes[ultimo].content).encode("ascii", "ignore").decode().lower()
    palabras = set(re.findall(r"[a-z0-9]+", consulta))
    permitidas = set("que cuales son los las mis factores de precio precios actuales disponibles tengo tenemos hay consulta consultar muestra muestrame ver lista listar catalogo el me puedes favor por porfavor".split())
    if "factores" not in palabras or not palabras <= permitidas:
        return herramientas
    if any(c.get("name") != "consultar_almacen" for m in mensajes[ultimo + 1:] for c in getattr(m, "tool_calls", [])):
        return herramientas
    return [h for h in herramientas if h.name == "consultar_almacen"]


def enlazar_herramientas(modelo, herramientas):
    if modelo is None:
        return None
    opciones = {"parallel_tool_calls": False} if isinstance(modelo, ChatOpenAI) else {}
    return modelo.bind_tools(herramientas, **opciones)
