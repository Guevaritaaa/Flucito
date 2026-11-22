"""Diario persistente de movimientos; una escritura incierta nunca se repite."""

import json
import uuid
import threading
import time
from functools import wraps

from langchain_core.runnables.config import ensure_config
from sqlalchemy import Column, MetaData, String, Table, Text, select

from app.core.database import engine

operaciones = Table(
    "operaciones_drive", MetaData(),
    Column("id", String(32), primary_key=True),
    Column("solicitud", String(64), index=True, nullable=False),
    Column("datos", Text, nullable=False),
)

_lock = threading.RLock()


def serializar(funcion):
    @wraps(funcion)
    def ejecutar(*args, **kwargs):
        with _lock:
            return funcion(*args, **kwargs)
    return ejecutar


def pendientes_archivo(archivo_id):
    operaciones.create(engine, checkfirst=True)
    with engine.connect() as db:
        filas = [json.loads(f[0]) for f in db.execute(select(operaciones.c.datos))]
    return [op for op in filas if op["archivo_id"] == archivo_id and op["estado"] == "pendiente_verificar"]


@serializar
def guardar(datos):
    # El commit ocurre antes de enviar la escritura a Drive. Si falla, no se mueve.
    operaciones.create(engine, checkfirst=True)
    with engine.begin() as db:
        existe = db.execute(select(operaciones.c.id).where(operaciones.c.id == datos["id"])).first()
        if existe:
            db.execute(operaciones.update().where(operaciones.c.id == datos["id"]).values(datos=json.dumps(datos)))
        else:
            solicitud = ensure_config().get("configurable", {}).get("drive_request_id", "sin-chat")
            db.execute(operaciones.insert().values(id=datos["id"], solicitud=solicitud, datos=json.dumps(datos)))


@serializar
def resultados(solicitud):
    operaciones.create(engine, checkfirst=True)
    with engine.connect() as db:
        datos = [json.loads(fila[0]) for fila in db.execute(select(operaciones.c.datos).where(operaciones.c.solicitud == solicitud))]
    return sorted(datos, key=lambda op: op.get("creada_ns", 0))


def resumen(operaciones_guardadas):
    # El diario conserva cada paso; el usuario recibe el resultado más reciente
    # de cada restauración, sin confundir errores ya recuperados con pendientes.
    restauraciones = {op["archivo_id"]: op for op in operaciones_guardadas if op.get("accion") == "restablecer_carpeta"}
    cubiertos = {item["id"] for op in restauraciones.values() for grupo in op.get("plan", {}).values() for item in grupo}
    operaciones_guardadas = [op for op in operaciones_guardadas
                            if (op.get("accion") == "restablecer_carpeta" and restauraciones[op["archivo_id"]]["id"] == op["id"])
                            or (op.get("accion") != "restablecer_carpeta" and op["archivo_id"] not in cubiertos)]
    lineas = []
    for op in operaciones_guardadas:
        nombre = op.get("nombre") or op["archivo_id"]
        destino = op.get("destino_nombre") or op["destino_id"]
        if op.get("accion") == "restablecer_carpeta":
            lineas.append(op.get("mensaje", f"Restauración {op['estado']}: {nombre}."))
            continue
        if op.get("accion") == "papelera":
            lineas.append(f"Papelera {op['estado']}: {nombre}.")
            continue
        if op["estado"] == "confirmada" and op.get("sin_cambios"):
            lineas.append(f"Ubicación confirmada: {nombre} ya está en {destino}; no se repitió el movimiento.")
        elif op["estado"] == "confirmada":
            lineas.append(f"Movimiento confirmado: {nombre} → {destino} (ubicación verificada en Drive).")
        elif op["estado"] == "fallida":
            lineas.append(f"Movimiento fallido: {nombre}. Drive rechazó la operación; no se confirmó ningún cambio.")
        else:
            lineas.append(f"Pendiente de verificar: {nombre} → {destino}. No se repetirá la escritura sin comprobar su ubicación en Drive.")
    estados = {op["estado"] for op in operaciones_guardadas}
    if "confirmada" in estados and len(estados) > 1:
        lineas.insert(0, "Resultado parcial: hay cambios confirmados y operaciones sin completar.")
    return "\n".join(lineas)


@serializar
def mover_verificado(cliente, archivo_id, destino_id, origen_esperado=None):
    op = {"id": uuid.uuid4().hex, "creada_ns": time.time_ns(), "archivo_id": archivo_id, "destino_id": destino_id, "estado": "pendiente_verificar"}
    def leer(file_id):
        return cliente.files().get(fileId=file_id, fields="id,name,parents,trashed,mimeType").execute(num_retries=3)
    # La caché nunca sustituye la lectura de la ubicación inicial.
    inicial = leer(archivo_id)
    destino = leer(destino_id)
    if inicial.get("trashed") or destino.get("trashed") or destino.get("mimeType") != "application/vnd.google-apps.folder":
        raise ValueError("El origen o destino ya no está disponible como se esperaba")
    padres = inicial.get("parents", [])
    pendientes = pendientes_archivo(archivo_id)
    for anterior in pendientes:
        if set(padres) == {anterior["destino_id"]}:
            anterior.update(estado="confirmada", padres_verificados=padres)
            guardar(anterior)
        else:
            # Incluso si sigue en origen, una escritura en vuelo podría completarse.
            guardar(op | {"nombre": inicial.get("name", archivo_id), "destino_nombre": destino.get("name", destino_id)})
            raise RuntimeError(resumen([anterior]))
    op.update(nombre=inicial.get("name", archivo_id), destino_nombre=destino.get("name", destino_id), padres_iniciales=padres)
    if destino_id in padres:
        op.update(estado="confirmada", sin_cambios=True, padres_verificados=padres)
        guardar(op)
        return op
    if origen_esperado and set(padres) != set(origen_esperado.split(",")):
        raise ValueError("La ubicación inicial cambió; vuelve a consultar Drive antes de mover")
    guardar(op)
    error_escritura = None
    try:
        cliente.files().update(fileId=archivo_id, addParents=destino_id, removeParents=",".join(padres), fields="id,parents").execute(num_retries=0)
    except Exception as error:
        error_escritura = error
    try:
        final = leer(archivo_id)
        op["padres_verificados"] = final.get("parents", [])
        if not final.get("trashed") and set(op["padres_verificados"]) == {destino_id}:
            op["estado"] = "confirmada"
        elif error_escritura and getattr(getattr(error_escritura, "resp", None), "status", None) in {400, 401, 403, 404}:
            op["estado"] = "fallida"
    except Exception:
        pass  # La escritura pudo completarse aunque se perdiera su respuesta.
    guardar(op)
    if op["estado"] != "confirmada":
        raise RuntimeError(resumen([op]))
    return op


def recuperar(solicitud):
    guardadas = resultados(solicitud)
    pendientes = [op for op in guardadas if op["estado"] == "pendiente_verificar"]
    if pendientes:
        from app.services.almacen.fuentes.google_drive_client import crear_cliente_drive
        try:
            cliente = crear_cliente_drive()
            for op in pendientes:
                if op.get("accion") == "restablecer_carpeta":
                    continue  # Requiere verificar el plan completo, no solo el padre.
                actual = cliente.files().get(fileId=op["archivo_id"], fields="parents,trashed").execute(num_retries=3)
                confirmado = actual.get("trashed") if op.get("accion") == "papelera" else (
                    not actual.get("trashed") and set(actual.get("parents", [])) == {op["destino_id"]}
                )
                if confirmado:
                    op.update(estado="confirmada", padres_verificados=actual.get("parents", []))
                    guardar(op)
        except Exception:
            pass
    return resumen(guardadas)


@serializar
def enviar_papelera_verificado(cliente, archivo_id, padre_esperado, solo_vacia=False):
    """Papelera reversible, sin reintentar la escritura y sin borrar carpetas con contenido."""
    from app.services.almacen.fuentes.google_drive_client import _listar_hijos
    def leer():
        return cliente.files().get(fileId=archivo_id, fields="id,name,parents,trashed").execute(num_retries=3)
    inicial = leer()
    op = {"id": uuid.uuid4().hex, "creada_ns": time.time_ns(), "accion": "papelera",
          "archivo_id": archivo_id, "destino_id": "papelera", "nombre": inicial.get("name", archivo_id),
          "estado": "pendiente_verificar"}
    if inicial.get("trashed"):
        op["estado"] = "confirmada"
        guardar(op)
        return op
    if inicial.get("parents") != [padre_esperado]:
        raise ValueError("El elemento cambió de ubicación antes de enviarlo a papelera")
    if pendientes_archivo(archivo_id):
        raise RuntimeError("Hay una escritura pendiente de verificar; no se repite")
    if solo_vacia and _listar_hijos(cliente, archivo_id):
        raise ValueError("La carpeta aún contiene archivos; se conserva")
    guardar(op)
    try:
        cliente.files().update(fileId=archivo_id, body={"trashed": True}, fields="id,trashed").execute(num_retries=0)
    except Exception as error:
        if getattr(getattr(error, "resp", None), "status", None) in {400, 401, 403, 404}:
            op["estado"] = "fallida"
    try:
        if leer().get("trashed"):
            op["estado"] = "confirmada"
    except Exception:
        pass
    guardar(op)
    if op["estado"] != "confirmada":
        raise RuntimeError(f"Papelera {op['estado']}: {op['nombre']}")
    return op
