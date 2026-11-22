"""Diagnóstico de solo lectura del MCP oficial, usando el OAuth existente de Drive."""

import json
import time
import requests
from google.auth.transport.requests import Request
from app.services.almacen.fuentes.google_drive_client import crear_cliente_drive

URL = "https://drivemcp.googleapis.com/mcp/v1"
HERRAMIENTAS_PERMITIDAS = {"search_files", "get_file"}


def invocar(metodo, params, credenciales, timeout=20):
    if metodo == "tools/call" and params.get("name") not in HERRAMIENTAS_PERMITIDAS:
        raise ValueError("La evaluación solo permite herramientas de lectura")
    if metodo not in {"initialize", "tools/list", "tools/call"}:
        raise ValueError("Método MCP no permitido")
    if not credenciales.valid:
        credenciales.refresh(Request())
    respuesta = requests.post(URL, headers={"Authorization": "Bearer " + credenciales.token,
        "Accept": "application/json, text/event-stream", "Content-Type": "application/json"},
        json={"jsonrpc": "2.0", "id": 1, "method": metodo, "params": params}, timeout=timeout)
    return respuesta.status_code, respuesta.json()


def main():
    credenciales = crear_cliente_drive()._http.credentials
    inicio = time.monotonic()
    estado, respuesta = invocar("initialize", {"protocolVersion": "2025-03-26", "capabilities": {},
        "clientInfo": {"name": "flucito-evaluacion", "version": "1.0"}}, credenciales)
    resultado = {"initialize_http": estado, "servidor": respuesta.get("result", {}).get("serverInfo", {}).get("name")}
    estado, respuesta = invocar("tools/call", {"name": "search_files", "arguments": {"query": "test", "pageSize": 1, "excludeContentSnippets": True}}, credenciales)
    contenido = respuesta.get("result", {})
    resultado.update(busqueda_http=estado, busqueda_error=bool(contenido.get("isError") or respuesta.get("error")),
                     duracion_s=round(time.monotonic()-inicio, 2))
    if resultado["busqueda_error"]:
        resultado["diagnostico"] = "Consulta rechazada por Google; revisar Drive MCP API y OAuth para agentes."
    print(json.dumps(resultado, ensure_ascii=False))
    return 1 if resultado["busqueda_error"] or estado != 200 else 0


if __name__ == "__main__":
    raise SystemExit(main())
