"""Versiones verificables de reportes y validación de correcciones de precios."""
from __future__ import annotations
import io
import json
import math
import os
from pathlib import Path
import re
import shutil
import threading
import uuid
import zipfile
from contextlib import contextmanager

import openpyxl
import pandas as pd
from fastapi import HTTPException
from openpyxl.utils import get_column_letter

from app.services.contexto_decisiones import contexto

PRECIOS = {"PRECIO COMPRA", "PUBLICO", "MINIMO", "MOSTRADOR", "MAYOREO", "DISTRIBUIDOR"}
_LOCK = threading.RLock()


@contextmanager
def bloquear_reporte(id):
    """Exclusión entre procesos; una interrupción no autoriza repetir escrituras."""
    ruta = directorio() / (id + ".lock")
    try:
        fd = os.open(ruta, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise HTTPException(409, "Este reporte ya se está validando. Consulta su estado antes de repetir la solicitud.") from exc
    try:
        os.close(fd)
        yield
    finally:
        ruta.unlink(missing_ok=True)


def directorio():
    from app.services.almacen.excel import CARPETA_DATOS
    return Path(CARPETA_DATOS) / ".revisiones"


def _guardar(meta):
    destino = directorio() / (meta["id"] + ".json")
    temporal = destino.with_suffix(".tmp")
    temporal.write_text(json.dumps(meta, ensure_ascii=False, default=str), encoding="utf-8")
    os.replace(temporal, destino)


def cargar(id, sid=None, uid=None, verificar=True):
    if not re.fullmatch(r"[a-f0-9]{32}", id):
        raise HTTPException(404, "Reporte no encontrado.")
    ruta = directorio() / (id + ".json")
    if not ruta.exists():
        raise HTTPException(404, "La versión del reporte ya no está disponible.")
    meta = json.loads(ruta.read_text(encoding="utf-8"))
    if verificar and (meta["usuario_id"] != uid or (sid is not None and meta["session_id"] != sid)):
        raise HTTPException(403, "Este reporte pertenece a otra conversación o usuario.")
    return meta


def registrar_reporte(ruta, meta_por_clave=None):
    ctx = contexto.get()
    if ctx is None:
        return
    wb = openpyxl.load_workbook(ruta)
    calculado = openpyxl.load_workbook(ruta, data_only=True)
    ws = wb.active
    columnas = [c.value for c in ws[1]]
    pendientes = []
    filas = []
    id = uuid.uuid4().hex
    for r in range(2, ws.max_row + 1):
        fila = [ws.cell(r, c).value for c in range(1, len(columnas) + 1)]
        faltantes = [nombre for c, nombre in enumerate(columnas) if nombre in PRECIOS and fila[c] is None]
        fila_id = uuid.uuid4().hex
        filas.append({"id": fila_id, "valores": fila})
        ws.cell(r, len(columnas) + 1, fila_id)
        if faltantes:
            pendientes.append({"producto": str(fila[columnas.index("Clave Artículo")]), "campos": faltantes})
    if not pendientes:
        calculado.close()
        wb.close()
        return
    ws.cell(1, len(columnas) + 1, "_FLUCITO_FILA")
    ws.column_dimensions[get_column_letter(len(columnas) + 1)].hidden = True
    firma = wb.create_sheet("_FLUCITO")
    firma.sheet_state = "veryHidden"
    firma.append([id, 1])
    wb.save(ruta)
    from app.services.almacen.excel import _inyectar_valores_cache_formulas
    cache = {c.coordinate: calculado[ws.title][c.coordinate].value for fila in ws for c in fila
             if c.data_type == "f" and isinstance(calculado[ws.title][c.coordinate].value, (int, float))}
    calculado.close()
    _inyectar_valores_cache_formulas(str(ruta), cache)
    directorio().mkdir(parents=True, exist_ok=True)
    copia = directorio() / (id + ".xlsx")
    shutil.copy2(ruta, copia)
    meta = {"id": id, "version": 1, "nombre": ruta.name, "origen": str(ruta.resolve()),
            "session_id": ctx["session_id"], "usuario_id": ctx["usuario_id"], "columnas": columnas,
            "filas": filas, "pendientes": pendientes, "drive": None, "estado": "pendiente"}
    meta["lote_id"] = ctx.setdefault("lote_id", uuid.uuid4().hex)
    meta["meta_por_clave"] = meta_por_clave or {}
    _guardar(meta)
    ctx.setdefault("reportes", []).append(id)


def id_archivo(ruta):
    if not Path(ruta).is_file():
        return None
    try:
        with open(Path(ruta), "rb") as stream:
            wb = openpyxl.load_workbook(stream, read_only=True)
            id = wb["_FLUCITO"].cell(1, 1).value if "_FLUCITO" in wb.sheetnames else None
            wb.close()
            return id
    except (OSError, ValueError, zipfile.BadZipFile):
        return None


def publico(meta):
    return {k: meta[k] for k in ("id", "version", "nombre", "pendientes", "estado")}


def revision_actual(ruta, sid, uid):
    id = id_archivo(ruta)
    if not id:
        return None
    meta = cargar(id, verificar=False)
    if meta["usuario_id"] != uid or meta["session_id"] != sid:
        return None
    salida = publico(meta)
    salida["relacionados"] = []
    for registro in directorio().glob("*.json"):
        otro = json.loads(registro.read_text(encoding="utf-8"))
        if otro["session_id"] == sid and otro["usuario_id"] == uid and otro["id"] != id and otro["pendientes"]:
            salida["relacionados"].append(publico(otro))
    return salida


def verificar_txt(ruta_excel, uid):
    id = id_archivo(ruta_excel)
    if id:
        meta = cargar(id, uid=uid)
        if meta["pendientes"] or meta["estado"] != "validado":
            raise HTTPException(409, "El reporte tiene precios pendientes. Sube el Excel corregido para validar y generar el TXT.")


def asociar_drive(ruta, archivo_id, carpeta_id):
    id = id_archivo(ruta)
    if id:
        meta = cargar(id, verificar=False)
        meta["drive"] = {"id": archivo_id, "carpeta_id": carpeta_id}
        _guardar(meta)


def validar_corregido(id, contenido, uid, propagar=True):
    """Valida todo antes de escribir; jamás usa los cachés de fórmulas subidos."""
    with _LOCK, bloquear_reporte(id):
        meta = cargar(id, uid=uid)
        if meta["estado"] == "validado":
            raise HTTPException(409, "Esta versión ya fue validada. Descarga el reporte actualizado.")
        try:
            with zipfile.ZipFile(io.BytesIO(contenido)) as z:
                if sum(f.file_size for f in z.infolist()) > 80 * 1024 * 1024 or any("vbaProject" in f.filename or "externalLinks/" in f.filename for f in z.infolist()):
                    raise ValueError("El archivo contiene macros, vínculos externos o excede el tamaño permitido.")
            wb = openpyxl.load_workbook(io.BytesIO(contenido), data_only=False, keep_links=False)
        except Exception as exc:
            raise HTTPException(422, "No se pudo leer el .xlsx. Usa el reporte descargado de esta tarjeta.") from exc
        if "_FLUCITO" not in wb.sheetnames or wb["_FLUCITO"].cell(1, 1).value != id or wb["_FLUCITO"].cell(1, 2).value != meta["version"]:
            raise HTTPException(422, "El archivo corresponde a otro reporte o versión.")
        ws = wb.active
        cols = meta["columnas"]
        if ws.max_row != len(meta["filas"]) + 1 or [c.value for c in ws[1]] != cols + ["_FLUCITO_FILA"]:
            raise HTTPException(422, "Se modificaron las filas o columnas del reporte.")
        originales = {f["id"]: f["valores"] for f in meta["filas"]}
        vistos, errores, datos = set(), [], []
        from app.services.almacen.factores import evaluar_aritmetica
        for r in range(2, ws.max_row + 1):
            fila_id = ws.cell(r, len(cols) + 1).value
            if fila_id not in originales or fila_id in vistos:
                raise HTTPException(422, "Los identificadores de productos fueron alterados o duplicados.")
            vistos.add(fila_id)
            original = originales[fila_id]
            clave = str(original[cols.index("Clave Artículo")])
            valores = [ws.cell(r, c).value for c in range(1, len(cols) + 1)]
            memo = {}
            def precio(c, pila=None):
                if c in memo:
                    return memo[c]
                pila = set() if pila is None else pila
                if c in pila:
                    raise ValueError("Dependencia circular")
                v = valores[c]
                if isinstance(v, str) and v.startswith("="):
                    if v != original[c]:
                        raise ValueError("Introduce un valor numérico para el precio corregido")
                    def referencia(m):
                        col, row = m.group(1), int(m.group(2))
                        indice = openpyxl.utils.column_index_from_string(col) - 1
                        if row != r or indice >= len(cols) or cols[indice] not in PRECIOS:
                            raise ValueError("Referencia no permitida")
                        return repr(precio(indice, pila | {c}))
                    v = evaluar_aritmetica(re.sub(r"\b([A-Z]+)(\d+)\b", referencia, v[1:]), 0)
                if v == 0 and original[c] == 0:
                    return 0.0
                if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v <= 0:
                    raise ValueError("Debe ser un número positivo y finito")
                memo[c] = float(v)
                return memo[c]
            for c, nombre in enumerate(cols):
                if nombre not in PRECIOS:
                    if str(valores[c] if valores[c] is not None else "") != str(original[c] if original[c] is not None else ""):
                        errores.append({"producto": clave, "campo": nombre, "motivo": "Solo se permiten correcciones de precios."})
                else:
                    try:
                        valores[c] = precio(c)
                    except (ValueError, TypeError, ZeroDivisionError, OverflowError) as exc:
                        errores.append({"producto": clave, "campo": nombre, "motivo": str(exc)})
            datos.append(valores)
        if errores:
            raise HTTPException(422, {"mensaje": "Corrige los campos indicados y vuelve a subir el Excel.", "errores": errores})
        # Escribir números verificados, sin depender del cálculo de Excel.
        for r, valores in enumerate(datos, 2):
            for c, valor in enumerate(valores, 1):
                if cols[c - 1] in PRECIOS:
                    ws.cell(r, c, valor)
                    ws.cell(r, c).comment = None
        wb["_FLUCITO"].cell(1, 2, meta["version"] + 1)
        staging = directorio() / (id + ".corregido.xlsx")
        wb.save(staging)
        # TXT listo únicamente después de validar todo el libro.
        from app.services.almacen.txt_aspel import generar_ambos_txt
        carpeta_txt = directorio() / id
        generar_ambos_txt(pd.DataFrame(datos, columns=cols), str(carpeta_txt), Path(meta["nombre"]).stem)
        meta["estado"] = "sincronizando" if meta["drive"] else "validado"
        if meta["drive"]:
            try:
                from app.services.almacen.fuentes.google_drive_client import crear_cliente_drive, subir_archivo
                from googleapiclient.http import MediaFileUpload
                cliente = crear_cliente_drive()
                from app.services.almacen.fuentes.navegador_drive import resolver_para_movimiento
                from app.core.config import settings
                resolver_para_movimiento(cliente, "id:" + meta["drive"]["carpeta_id"], settings.google_drive_folder_id)
                actual_drive = cliente.files().get(fileId=meta["drive"]["id"], fields="id,parents,trashed").execute(num_retries=3)
                if actual_drive.get("trashed") or meta["drive"]["carpeta_id"] not in actual_drive.get("parents", []):
                    raise ValueError("El reporte cambió de ubicación en Drive")
                cliente.files().update(fileId=meta["drive"]["id"], media_body=MediaFileUpload(str(staging))).execute(num_retries=3)
                for txt in carpeta_txt.glob("*.txt"):
                    from app.services.almacen.fuentes.google_drive_client import _listar_hijos
                    existentes = [a for a in _listar_hijos(cliente, meta["drive"]["carpeta_id"]) if a.get("name") == txt.name]
                    if len(existentes) > 1:
                        raise ValueError("Hay TXT homónimos que requieren revisión")
                    if existentes:
                        cliente.files().update(fileId=existentes[0]["id"], media_body=MediaFileUpload(str(txt))).execute(num_retries=3)
                    else:
                        subir_archivo(cliente, txt, meta["drive"]["carpeta_id"])
                meta["estado"] = "validado"
            except Exception as exc:
                staging.unlink(missing_ok=True)
                raise HTTPException(503, "Los precios son válidos, pero Drive no pudo actualizarse. Vuelve a intentar la validación; el TXT sigue bloqueado.") from exc
        os.replace(staging, directorio() / (id + ".xlsx"))
        origen = Path(meta["origen"])
        if origen.exists() and id_archivo(origen) == id:
            shutil.copy2(directorio() / (id + ".xlsx"), origen)
        from app.services.almacen.excel import CARPETA_DATOS, NOMBRE_ARCHIVO_BASE
        base = Path(CARPETA_DATOS) / NOMBRE_ARCHIVO_BASE
        if id_archivo(base) == id:
            shutil.copy2(directorio() / (id + ".xlsx"), base)
            for txt in carpeta_txt.glob("*.txt"):
                shutil.copy2(txt, Path(CARPETA_DATOS) / txt.name)
        meta.update(version=meta["version"] + 1, pendientes=[])
        _guardar(meta)
        if propagar:
            _propagar_correcciones(meta, datos, uid)
        return publico(meta)


def _propagar_correcciones(meta, datos, uid):
    """Actualiza las proyecciones del mismo lote solo si coinciden sus datos originales."""
    cols = meta["columnas"]
    clave_idx = cols.index("Clave Artículo")
    mapa = {str(f[clave_idx]): f for f in datos}
    for archivo in directorio().glob("*.json"):
        otro = json.loads(archivo.read_text(encoding="utf-8"))
        if otro["id"] == meta["id"] or not otro["pendientes"] or otro.get("lote_id") != meta.get("lote_id") or otro["columnas"] != cols:
            continue
        if any(str(f["valores"][clave_idx]) not in mapa or any(str(f["valores"][c] or "") != str(mapa[str(f["valores"][clave_idx])][c] or "") for c, nombre in enumerate(cols) if nombre not in PRECIOS) for f in otro["filas"]):
            continue
        wb = openpyxl.load_workbook(directorio() / (otro["id"] + ".xlsx"))
        for r, f in enumerate(otro["filas"], 2):
            for c, nombre in enumerate(cols, 1):
                if nombre in PRECIOS:
                    wb.active.cell(r, c, mapa[str(f["valores"][clave_idx])][c - 1])
        contenido = io.BytesIO()
        wb.save(contenido)
        try:
            validar_corregido(otro["id"], contenido.getvalue(), uid, propagar=False)
        except HTTPException:
            # La tarjeta del reporte asociado conserva su estado pendiente y permite reintentar.
            continue
