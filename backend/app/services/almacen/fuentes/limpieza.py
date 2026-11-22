"""Restauracion selectiva en DOCUMENTOS ENTRADA, sin mover carpetas de fecha."""

import re
import time
import uuid
from pathlib import Path

from app.core.config import settings
from app.agents.actividad import emitir_paso
from app.services.almacen.excel import CARPETA_DATOS
from app.services.almacen.fuentes.estado_drive import NOMBRE_ESTADO, cargar_estado, guardar_estado
from app.services.almacen.fuentes.google_drive_client import (
    MIME_CARPETA, CARPETA_REPORTES_HISTORICOS, crear_cliente_drive,
    _listar_hijos, buscar_carpeta_hija, listar_carpetas_fecha_en_historico,
    extraer_anio_mes_de_fecha_carpeta,
)
from app.services.almacen.fuentes.navegador_drive import resolver_para_movimiento, RutaAmbigua
from app.services.almacen.fuentes.operaciones_drive import (
    guardar, mover_verificado, enviar_papelera_verificado, serializar,
)


def es_reporte_generado(nombre):
    # Nunca clasificar un TXT de apoyo por su extension solamente.
    return bool(re.fullmatch(r"ENTRADAS_ALMACEN_.+(?:\.xlsx|_(?:COMAS|TABS)\.txt)", nombre, re.IGNORECASE))


def _plan(cliente, carpeta):
    documentos, reportes, subcarpetas, desconocidos = [], [], [], []
    vistos = set()
    def recorrer(padre, nivel=0):
        if padre in vistos:
            raise ValueError("La estructura contiene referencias repetidas")
        vistos.add(padre)
        for item in _listar_hijos(cliente, padre):
            elemento = {**item, "padre_id": padre, "nivel": nivel}
            if item.get("mimeType") == MIME_CARPETA:
                # Una fecha anidada no es una carpeta de proveedor.
                if extraer_anio_mes_de_fecha_carpeta(item["name"]):
                    raise ValueError("Hay otra carpeta de fecha anidada; debe resolverse antes de restaurar")
                subcarpetas.append(elemento)
                recorrer(item["id"], nivel + 1)
            elif es_reporte_generado(item["name"]):
                reportes.append(elemento)
            elif Path(item["name"]).suffix.lower() in {".xml", ".pdf", ".txt"}:
                documentos.append(elemento)
            else:
                desconocidos.append(elemento)
    recorrer(carpeta["id"])
    # Drive tolera homonimos, pero no elegimos ni sobrescribimos un original.
    nombres = [d["name"].casefold() for d in documentos]
    if len(nombres) != len(set(nombres)):
        raise ValueError("Hay documentos originales con el mismo nombre; elige como distinguirlos antes de restaurar")
    if desconocidos:
        raise ValueError("Hay archivos ajenos a los reportes u originales reconocidos; se conservan sin cambios: " + ", ".join(i["name"] for i in desconocidos))
    return {"documentos": documentos, "reportes": reportes, "subcarpetas": subcarpetas}


def _leer(cliente, archivo_id):
    return cliente.files().get(fileId=archivo_id, fields="id,name,parents,trashed,mimeType").execute(num_retries=3)


def _invalidar_estado(documentos):
    ruta = Path(CARPETA_DATOS) / NOMBRE_ESTADO
    if ruta.is_file():
        estado = cargar_estado(ruta)
        for documento in documentos:
            estado["archivos"].pop(documento["id"], None)
        guardar_estado(ruta, estado)


@serializar
def restaurar_carpetas(rutas, cliente=None, carpeta_raiz_id=None):
    """Prevalida toda la seleccion antes de modificar; permite retomar resultados parciales."""
    cliente = cliente or crear_cliente_drive()
    raiz = carpeta_raiz_id or settings.google_drive_folder_id
    if not raiz:
        raise ValueError("Falta GOOGLE_DRIVE_FOLDER_ID")
    if not rutas:
        raise ValueError("Indica al menos una carpeta de fecha")
    carpetas, planes, ids = [], [], set()
    busqueda_id = uuid.uuid4().hex
    emitir_paso(busqueda_id, "buscar", "en_curso")
    try:
        for ruta in rutas:
            carpeta = resolver_para_movimiento(cliente, ruta, raiz)
            fecha = extraer_anio_mes_de_fecha_carpeta(carpeta["nombre"])
            if not carpeta["es_carpeta"] or not fecha:
                raise ValueError("Selecciona una carpeta de fecha, no un contenedor ni un proveedor")
            anio, mes = fecha
            esperada = f"{CARPETA_REPORTES_HISTORICOS}/{anio}/{mes}/{carpeta['nombre']}"
            if carpeta["ruta_completa"].casefold() != esperada.casefold():
                raise ValueError("La carpeta debe estar en DOCUMENTOS ENTRADA/ANIO/MES/FECHA; no se movera automaticamente")
            if carpeta["id"] not in ids:
                ids.add(carpeta["id"])
                carpetas.append(carpeta)
                planes.append(_plan(cliente, carpeta))
    except RutaAmbigua as error:
        emitir_paso(busqueda_id, "buscar", "pendiente_verificar")
        return {"ok": False, "tipo": "restablecer_carpeta", "requiere_confirmacion": True,
                "candidatos": error.candidatos, "mensaje": "Elige la carpeta por ruta completa o id:ID. No se modifico ninguna carpeta."}

    except Exception:
        emitir_paso(busqueda_id, "buscar", "error")
        raise
    emitir_paso(busqueda_id, "buscar", "completado")
    salidas = []
    for carpeta, plan in zip(carpetas, planes):
        op = {"id": uuid.uuid4().hex, "creada_ns": time.time_ns(), "accion": "restablecer_carpeta",
              "archivo_id": carpeta["id"], "destino_id": carpeta["id"], "nombre": carpeta["nombre"],
              "ruta": carpeta["ruta_completa"], "plan": plan, "estado": "pendiente_verificar",
              "mensaje": f"Restauracion pendiente de verificar: {carpeta['ruta_completa']}."}
        guardar(op)
        emitir_paso(op["id"] + ":restaurar", "restaurar", "en_curso")
        verificando = False
        try:
            for documento in plan["documentos"]:
                mover_verificado(cliente, documento["id"], carpeta["id"], documento["padre_id"])
            # Todos los originales quedan fuera de las carpetas antes de retirar reportes.
            for reporte in plan["reportes"]:
                enviar_papelera_verificado(cliente, reporte["id"], reporte["padre_id"])
            for sub in sorted(plan["subcarpetas"], key=lambda c: c["nivel"], reverse=True):
                enviar_papelera_verificado(cliente, sub["id"], sub["padre_id"], solo_vacia=True)
            emitir_paso(op["id"] + ":verificar", "verificar", "en_curso")
            verificando = True
            actual = _leer(cliente, carpeta["id"])
            hijos = _listar_hijos(cliente, carpeta["id"])
            esperados = {d["id"] for d in plan["documentos"]}
            if actual.get("trashed") or actual.get("parents") != [carpeta["padre_id"]] or {h["id"] for h in hijos} != esperados:
                raise RuntimeError("La comprobacion final no coincide con los documentos y ubicacion esperados")
            _invalidar_estado(plan["documentos"])
            op.update(estado="confirmada", mensaje=f"Carpeta restablecida: {carpeta['ruta_completa']}. Quedan {len(esperados)} originales XML/PDF/TXT; {len(plan['reportes'])} reportes y {len(plan['subcarpetas'])} subcarpetas enviados a papelera. Ubicacion y contenido verificados; lista para reprocesar.")
        except Exception as error:
            op.update(estado="parcial", mensaje=f"Restauracion incompleta: {carpeta['ruta_completa']}. {error}. Se conservaron los originales y la carpeta de fecha; faltan pasos por verificar o completar.")
        guardar(op)
        estado_paso = "completado" if op["estado"] == "confirmada" else "parcial"
        emitir_paso(op["id"] + ":restaurar", "restaurar", estado_paso)
        if verificando:
            emitir_paso(op["id"] + ":verificar", "verificar", estado_paso)
        salidas.append(op)
    return {"ok": all(op["estado"] == "confirmada" for op in salidas), "tipo": "restablecer_carpeta",
            "estado": "confirmada" if all(op["estado"] == "confirmada" for op in salidas) else "parcial",
            "carpetas": salidas, "mensaje": "\n".join(op["mensaje"] for op in salidas)}


def restaurar_entorno_pruebas():
    """Aplica la misma restauracion a todas las fechas actuales, sin borrar configuracion local."""
    cliente = crear_cliente_drive()
    raiz = settings.google_drive_folder_id
    historico = buscar_carpeta_hija(cliente, CARPETA_REPORTES_HISTORICOS, raiz)
    if not historico:
        return {"ok": False, "error": "No existe DOCUMENTOS ENTRADA"}
    fechas = listar_carpetas_fecha_en_historico(cliente, historico, fn_listar_hijos=_listar_hijos)
    rutas = ["id:" + c["id"] for c in fechas]
    if not rutas:
        return {"ok": True, "tipo": "restablecer_carpeta", "carpetas": [], "mensaje": "No hay carpetas de fecha para restablecer."}
    return restaurar_carpetas(rutas, cliente, raiz)
