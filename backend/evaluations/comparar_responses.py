"""Compara modelos reales con las mismas herramientas y datos de prueba aislados.

Sin --live solo guarda el protocolo. Con --live consume tokens de OpenAI,
pero sustituye las seis herramientas por fixtures y nunca escribe en Drive.
"""

import argparse
import json
import statistics
import time
from pathlib import Path

from langchain_core.messages import HumanMessage
from langchain_core.tools import StructuredTool
from openai import OpenAI

from app.agents.ejecucion_tools import ejecutar_herramientas
from app.agents.llm_router import crear_llm_openai
from app.agents.prompts import SYSTEM_PROMPT
from app.agents.seleccion_tools import enlazar_herramientas, seleccionar_herramientas
from app.agents.tools import HERRAMIENTAS
from app.core.config import settings

CASOS = Path(__file__).with_name("casos_responses.json")


def herramientas_aisladas(registro):
    def implementar(nombre):
        def ejecutar(**args):
            registro.append({"name": nombre, "args": args})
            if nombre == "consultar_almacen":
                datos = {"ok": True, "tipo_consulta": "catalogo_factores", "factores_disponibles": {"FESTO": {"PUBLICO": "{COSTEO}/.7"}}}
            elif nombre == "consultar_drive":
                datos = {"ok": True, "tipo": "busqueda_historica" if args.get("modo_consulta") == "buscar_reportes_excel" else "explorar_estructura",
                         "fecha": "17-11-2026", "ruta": "DOCUMENTOS ENTRADA/2026/NOVIEMBRE/17-11-2026",
                         "reportes": [{"id": "fixture-excel", "nombre": "ENTRADAS_ALMACEN_17-11-2026.xlsx", "fecha": "17-11-2026"}]}
            elif nombre == "generar_entradas_almacen":
                datos = {"ok": True, "reporte_generado": True, "fecha": "17-11-2026", "productos": 2, "resumen": {"productos": 2}}
            elif nombre == "gestionar_archivos_drive" and args.get("accion") == "restablecer_carpeta":
                datos = {"ok": True, "estado": "confirmada", "mensaje": "Carpeta 17-11-2026 restablecida en DOCUMENTOS ENTRADA/2026/NOVIEMBRE/17-11-2026: 2 originales y 6 reportes en papelera. Verificado."}
            else:
                datos = {"ok": False, "error": "Acción fuera del escenario de prueba; no se modificó ningún recurso real."}
            return json.dumps(datos, ensure_ascii=False)
        return ejecutar
    return [StructuredTool.from_function(implementar(t.name), name=t.name, description=t.description, args_schema=t.args_schema) for t in HERRAMIENTAS]


def ejecutar_caso(caso, modelo, precios=None):
    from langchain_core.messages import SystemMessage
    registro = []
    tools = herramientas_aisladas(registro)
    mensajes = [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=caso["solicitud"])]
    inicio = time.perf_counter()
    uso = {"input_tokens": 0, "output_tokens": 0, "cached_tokens": 0}
    hubo_uso = True
    texto = ""
    error = None
    try:
        for _ in range(5):
            seleccion = seleccionar_herramientas(mensajes, tools)
            ai = enlazar_herramientas(modelo, seleccion).invoke(mensajes)
            metadata = ai.usage_metadata
            hubo_uso &= bool(metadata)
            if metadata:
                uso["input_tokens"] += metadata.get("input_tokens", 0)
                uso["output_tokens"] += metadata.get("output_tokens", 0)
                uso["cached_tokens"] += (metadata.get("input_token_details") or {}).get("cache_read", 0)
            mensajes.append(ai)
            if not ai.tool_calls:
                texto = str(ai.text)
                break
            mensajes.extend(ejecutar_herramientas({"messages": mensajes}, tools)["messages"])
        else:
            error = "round_limit"
    except Exception as exc:
        hubo_uso = False
        error = f"{type(exc).__name__}:{getattr(exc, 'status_code', 'no_status')}"
    esperadas = caso["herramientas"]
    correctas = len(registro) == len(esperadas) and all(
        real["name"] == esperado["name"] and all(real["args"].get(k) == v for k, v in esperado["args"].items())
        for real, esperado in zip(registro, esperadas)
    )
    completada = error is None and bool(texto) and correctas and all(t.lower() in texto.lower() for t in caso["texto_esperado"])
    costo = None
    if precios is not None and hubo_uso and error is None:
        costo = ((uso["input_tokens"] - uso["cached_tokens"]) * precios["input_per_million"] + uso["cached_tokens"] * precios.get("cached_input_per_million", precios["input_per_million"]) + uso["output_tokens"] * precios["output_per_million"]) / 1_000_000
    return {"caso": caso["id"], "completada": completada, "herramientas_correctas": correctas,
            "latencia_ms": round((time.perf_counter() - inicio) * 1000, 2), "uso": uso if hubo_uso else None,
            "costo_usd": costo, "error": error}


def resumen(filas):
    resueltas = sum(f["completada"] for f in filas)
    costo = sum(f["costo_usd"] for f in filas) if filas and all(f["costo_usd"] is not None for f in filas) else None
    return {"tareas": len(filas), "resueltas": resueltas,
            "exactitud_fixture": resueltas / len(filas) if filas else None,
            "latencia_mediana_ms": statistics.median(f["latencia_ms"] for f in filas) if filas else None,
            "costo_por_tarea_resuelta_usd": costo / resueltas if costo is not None and resueltas else None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--output", type=Path, default=Path("datos/evaluaciones/responses.json"))
    parser.add_argument("--precios", type=Path, help="JSON por modelo con input_per_million, output_per_million y cached_input_per_million opcional; USD")
    parser.add_argument("--repeticiones", type=int, default=1, choices=range(1, 11))
    args = parser.parse_args()
    casos = json.loads(CASOS.read_text(encoding="utf-8"))
    precios = json.loads(args.precios.read_text(encoding="utf-8")) if args.precios else {}
    modelos = ["gpt-5.6-luna", "gpt-6-luna"]
    reporte = {"estado": "protocolo", "api": "responses", "modelos": modelos, "casos": casos, "resultados": {},
               "alcance": "Herramientas y datos aislados. Exactitud automática sobre fixtures; requiere revisión humana y validación de la cuenta/Drive real.",
               "costos": "null si faltan tarifas explícitas o uso verificable; no se inventan precios ni mediciones."}
    if args.live:
        try:
            disponibles = {m.id for m in OpenAI(api_key=settings.openai_api_key, timeout=20, max_retries=0).models.list()}
            faltantes = [m for m in modelos if m not in disponibles]
            if faltantes:
                reporte.update(estado="modelos_no_disponibles", modelos_faltantes=faltantes)
            else:
                reporte["estado"] = "evaluado"
                for nombre in modelos:
                    modelo = crear_llm_openai(nombre, True)
                    filas = [ejecutar_caso(caso, modelo, precios.get(nombre)) for _ in range(args.repeticiones) for caso in casos]
                    reporte["resultados"][nombre] = {"casos": filas, "resumen": resumen(filas)}
        except Exception as exc:
            reporte.update(estado="cuenta_no_validada", error={"tipo": type(exc).__name__, "status": getattr(exc, "status_code", None)})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(reporte, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"estado": reporte["estado"], "archivo": str(args.output)}, ensure_ascii=False))
    return 0 if reporte["estado"] in {"protocolo", "evaluado"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
