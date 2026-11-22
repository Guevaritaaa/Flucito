"""Valida todo el lote antes de ejecutar y conserva la relación call_id/resultado."""

import json

from langchain_core.messages import ToolMessage
from pydantic import ValidationError


def ejecutar_herramientas(state, herramientas, config=None):
    mensaje = state["messages"][-1]
    llamadas = getattr(mensaje, "tool_calls", [])
    disponibles = {h.name: h for h in herramientas}
    ids = [c.get("id") for c in llamadas]
    anteriores = {m.tool_call_id for m in state["messages"] if isinstance(m, ToolMessage)}
    if any(not isinstance(id, str) or not id for id in ids) or len(set(ids)) != len(ids) or anteriores.intersection(ids):
        raise ValueError("Las llamadas deben tener identificadores únicos; no se ejecutó el lote")
    validadas = []
    try:
        for llamada in llamadas:
            herramienta = disponibles[llamada["name"]]
            args = herramienta.args_schema.model_validate(llamada["args"], strict=True, extra="forbid")
            validadas.append({**llamada, "args": args.model_dump(exclude_unset=True), "type": "tool_call"})
    except (KeyError, ValidationError, TypeError, ValueError):
        # No devolver argumentos ni detalles de validación que puedan contener datos privados.
        return {"messages": [ToolMessage(content=json.dumps({"ok": False, "error": "Lote inválido: revisa nombres y argumentos; no se ejecutó ninguna herramienta."}),
                                         tool_call_id=c["id"], name=c.get("name"), status="error") for c in llamadas]}

    salidas = []
    detener = False
    for llamada in validadas:
        if detener:
            salida = ToolMessage(content='{"ok": false, "error": "No ejecutada: una llamada anterior falló o requiere una decisión del usuario."}',
                                 tool_call_id=llamada["id"], name=llamada["name"], status="error")
        else:
            # BaseTool mantiene callbacks y configuración de LangGraph; devuelve el mismo call_id.
            try:
                salida = disponibles[llamada["name"]].invoke(llamada, config=config)
            except Exception:
                salida = ToolMessage(content='{"ok": false, "error": "La herramienta no pudo completar la operación. Comprueba su resultado antes de repetirla."}',
                                     tool_call_id=llamada["id"], name=llamada["name"], status="error")
            detener = salida.status == "error"
            try:
                datos = json.loads(salida.content)
                if isinstance(datos, dict):
                    detener |= datos.get("ok") is False or bool(datos.get("requiere_confirmacion") or datos.get("cancelado_por_usuario"))
            except (TypeError, ValueError):
                pass
        salidas.append(salida)
    return {"messages": salidas}
