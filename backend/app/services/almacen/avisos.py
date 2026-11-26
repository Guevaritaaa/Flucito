"""Avisos de estado para el chat y su historial, sin depender del texto del modelo."""


def avisos_estado(interaccion=None, revision=None, resumen=None):
    avisos = []
    if interaccion and interaccion.get("estado") == "pendiente":
        for pregunta in interaccion.get("preguntas", []):
            if pregunta.get("tipo") == "linea":
                avisos.append({"nivel": "advertencia", "titulo": pregunta["titulo"],
                    "descripcion": pregunta.get("explicacion") or "No hay una línea confirmada para este producto.",
                    "accion": "Confirma una referencia en la tarjeta o elige completar el Excel manualmente."})
        if any(p.get("tipo") == "factor" for p in interaccion.get("preguntas", [])):
            avisos.append({"nivel": "advertencia", "titulo": "Factor por confirmar",
                "descripcion": "Falta decidir cómo calcular los precios de venta de las líneas indicadas.",
                "accion": "Elige un factor o continúa con precios manuales en la tarjeta."})
    if revision and revision.get("pendientes"):
        avisos.append({"nivel": "advertencia", "titulo": "El reporte tiene campos pendientes",
            "descripcion": f"{revision['nombre']}: {len(revision['pendientes'])} producto(s) requieren revisión. Los TXT siguen pendientes.",
            "accion": "Completa únicamente las líneas pendientes y los precios vacíos, y adjunta el Excel corregido."})
    for texto in (resumen or {}).get("explicaciones_productos", []):
        if "incompleta" in texto:
            avisos.append({"nivel": "advertencia", "titulo": "Clave completada con las fuentes disponibles",
                "descripcion": texto, "accion": "Revisa la procedencia en los comentarios del Excel."})
    return avisos
