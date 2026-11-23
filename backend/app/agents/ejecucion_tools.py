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
    from app.services.contexto_decisiones import contexto
    if contexto.get() is not None and contexto.get().get("interaccion"):
        return {"messages": [ToolMessage(content='{"ok": false, "error": "Hay decisiones pendientes en la tarjeta. Espera la confirmación del usuario antes de continuar."}', tool_call_id=c["id"], name=c.get("name"), status="error") for c in llamadas]}
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
                    if datos.get("requiere_confirmacion"):
                        from app.services.contexto_decisiones import contexto
                        from app.services.decisiones import registrar
                        ctx = contexto.get()
                        if ctx is not None:
                            argumentos = ctx.get("continuacion") if llamada["name"] == "generar_entradas_almacen" else llamada["args"]
                            ctx["interaccion"] = registrar(ctx["session_id"], ctx["usuario_id"], datos, llamada["name"], argumentos or llamada["args"])
            except (TypeError, ValueError):
                pass
        salidas.append(salida)
    return {"messages": salidas}
