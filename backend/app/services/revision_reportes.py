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
        if "Línea" in columnas and not str(fila[columnas.index("Línea")] or "").strip():
            faltantes.insert(0, "Línea")
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
    meta["lineas_editables"] = [p["producto"] for p in pendientes if "Línea" in p["campos"]]
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
    salida = {k: meta[k] for k in ("id", "version", "nombre", "pendientes", "estado")}
    salida["factores_pendientes"] = meta.get("factores_pendientes", [])
    salida["resumen_revision"] = meta.get("resumen_revision", "")
    return salida


def _factor_linea(codigo, factores, uid):
    from app.services.almacen.factores import obtener_catalogo_lineas, normalizar_eleccion_factor
    if codigo in (factores or {}):
        factor = normalizar_eleccion_factor(factores[codigo])
        if factor is None:
            raise HTTPException(422, "Selecciona un factor válido.")
        return factor
    # El código escrito se conserva exactamente: no expandirlo por prefijo.
    if uid is not None:
        from app.services.decisiones import SessionLocal, clave_preferencia
        from app.models.preferencia import PreferenciaDecision
        from sqlalchemy import select
        with SessionLocal() as db:
            pref = db.scalar(select(PreferenciaDecision).where(PreferenciaDecision.usuario_id == uid,
                PreferenciaDecision.clave == clave_preferencia("factor", {"linea": codigo})))
            if pref:
                respuesta = json.loads(pref.respuesta_json)
                from app.services.decisiones import validar_factor
                return validar_factor(respuesta.get("campos", {})) if respuesta["opcion"] == "custom" else "LLENADO_MANUAL" if respuesta["opcion"] == "manual" else normalizar_eleccion_factor(respuesta["opcion"])
    return obtener_catalogo_lineas().get(codigo, {}).get("factor")


def _copiar_version(meta):
    from app.services.almacen.excel import CARPETA_DATOS, NOMBRE_ARCHIVO_BASE
    copia = directorio() / (meta["id"] + ".xlsx")
    for ruta in (Path(meta["origen"]), Path(CARPETA_DATOS) / NOMBRE_ARCHIVO_BASE):
        if ruta.exists() and id_archivo(ruta) == meta["id"]:
            shutil.copy2(copia, ruta)


def reanudar_revision(reporte_id, version, factores_elegidos, uid):
    meta = cargar(reporte_id, uid=uid)
    if version != meta["version"] or meta["estado"] != "factor_pendiente":
        raise HTTPException(409, "La versión revisada cambió. Recarga la tarjeta del reporte.")
    return validar_corregido(reporte_id, (directorio() / (reporte_id + ".xlsx")).read_bytes(), uid,
                            factores_elegidos=factores_elegidos)


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


def validar_corregido(id, contenido, uid, propagar=True, factores_elegidos=None):
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
        factores_pendientes, pendientes, explicaciones = {}, [], []
        factores = {**meta.get("factores_elegidos", {}), **(factores_elegidos or {})}
        ventas = PRECIOS - {"PRECIO COMPRA"}
        from app.services.almacen.factores import evaluar_aritmetica
        for r in range(2, ws.max_row + 1):
            fila_id = ws.cell(r, len(cols) + 1).value
            if fila_id not in originales or fila_id in vistos:
                raise HTTPException(422, "Los identificadores de productos fueron alterados o duplicados.")
            vistos.add(fila_id)
            original = originales[fila_id]
            clave = str(original[cols.index("Clave Artículo")])
            valores = [ws.cell(r, c).value for c in range(1, len(cols) + 1)]
            editable = clave in meta.get("lineas_editables", [])
            compra_idx = cols.index("PRECIO COMPRA")
            if editable and original[compra_idx] is not None and valores[compra_idx] != original[compra_idx]:
                errores.append({"producto": clave, "campo": "PRECIO COMPRA", "motivo": "Conserva el costo de compra extraído."})
            factor = None
            permitir_vacios = False
            if editable:
                from app.services.almacen.lineas import normalizar_linea
                from app.services.almacen.factores import calcular_precios_numericos
                try:
                    codigo = normalizar_linea(valores[cols.index("Línea")])
                except ValueError as exc:
                    errores.append({"producto": clave, "campo": "Línea", "motivo": str(exc)})
                    codigo = ""
                valores[cols.index("Línea")] = codigo
                if codigo:
                    factor = _factor_linea(codigo, factores, uid)
                    faltan_ventas = any(valores[cols.index(p)] is None for p in ventas)
                    if faltan_ventas and factor is None:
                        factores_pendientes[codigo] = {"linea": codigo, "descripcion": "Línea escrita en el Excel revisado"}
                        explicaciones.append(f"{clave}: guardé la línea {codigo}. Falta elegir su factor; conservé los precios ya escritos.")
                    permitir_vacios = faltan_ventas and factor in (None, "LLENADO_MANUAL")
                    if factor and factor not in {"LLENADO_MANUAL", "SIN_FACTOR"}:
                        compra = valores[cols.index("PRECIO COMPRA")]
                        if isinstance(compra, str) and compra.startswith("=") and compra == original[compra_idx]:
                            try:
                                from app.services.almacen.factores import evaluar_aritmetica
                                compra = evaluar_aritmetica(compra[1:], 0)
                            except (ValueError, TypeError, ZeroDivisionError, OverflowError):
                                compra = None
                        if isinstance(compra, (int, float)) and not isinstance(compra, bool) and math.isfinite(compra) and compra > 0:
                            calculados = calcular_precios_numericos(factor, compra)
                            completados = []
                            for p in ventas:
                                if valores[cols.index(p)] is None:
                                    valores[cols.index(p)] = calculados[p]
                                    completados.append(p)
                            if completados:
                                explicaciones.append(f"{clave}: línea {codigo}, factor {factor}; completé {', '.join(sorted(completados))}. Conservé los precios escritos por el asesor.")
                    if not faltan_ventas:
                        explicaciones.append(f"{clave}: línea {codigo}; conservé los cinco precios de venta escritos por el asesor.")
                    info = meta.setdefault("meta_por_clave", {}).setdefault(clave, {})
                    info.update(origen_linea="ASESOR_EXCEL", linea_confirmada=codigo,
                                confirmacion_asesor=True, usuario_confirmacion=uid, factor=factor or "LLENADO_MANUAL")
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
                    if not (nombre == "Línea" and editable) and str(valores[c] if valores[c] is not None else "") != str(original[c] if original[c] is not None else ""):
                        errores.append({"producto": clave, "campo": nombre, "motivo": "Solo se permiten correcciones de precios."})
                else:
                    if nombre in ventas and valores[c] is None and permitir_vacios:
                        continue
                    try:
                        valores[c] = precio(c)
                    except (ValueError, TypeError, ZeroDivisionError, OverflowError) as exc:
                        errores.append({"producto": clave, "campo": nombre, "motivo": str(exc)})
            datos.append(valores)
            campos = [p for p in ventas if valores[cols.index(p)] is None]
            if campos:
                pendientes.append({"producto": clave, "campos": sorted(campos)})
        if errores:
            raise HTTPException(422, {"mensaje": "Corrige los campos indicados y vuelve a subir el Excel.", "errores": errores})
        # Escribir números verificados, sin depender del cálculo de Excel.
        for r, valores in enumerate(datos, 2):
            for c, valor in enumerate(valores, 1):
                if cols[c - 1] in PRECIOS or (cols[c - 1] == "Línea" and str(valores[cols.index("Clave Artículo")]) in meta.get("lineas_editables", [])):
                    ws.cell(r, c).value = valor
            clave = str(valores[cols.index("Clave Artículo")])
            from app.services.almacen.procedencia import explicar_producto
            from openpyxl.comments import Comment
            explicacion = explicar_producto(clave, meta.get("meta_por_clave", {}).get(clave, {}))
            detalles = [e for e in explicaciones if e.startswith(clave + ":")]
            for campo in ("Línea", *PRECIOS):
                celda = ws.cell(r, cols.index(campo) + 1)
                if celda.value is not None:
                    celda.comment = Comment(" ".join([explicacion, *detalles]).strip() or "Precio revisado por el asesor.", "Flucito")
        wb["_FLUCITO"].cell(1, 2, meta["version"] + 1)
        staging = directorio() / (id + ".corregido.xlsx")
        wb.save(staging)
        meta["resumen_revision"] = f"Reporte {meta['nombre']}. " + " ".join(explicaciones)
        if pendientes:
            # Se conserva la versión recibida, incluidos los precios manuales; la
            # continuación nunca vuelve al Excel anterior ni a los documentos fuente.
            os.replace(staging, directorio() / (id + ".xlsx"))
            meta.update(version=meta["version"] + 1, pendientes=pendientes,
                        factores_pendientes=list(factores_pendientes.values()),
                        factores_elegidos=factores,
                        estado="factor_pendiente" if factores_pendientes else "pendiente")
            revisadas = {ws.cell(r, len(cols) + 1).value: valores for r, valores in enumerate(datos, 2)}
            for f in meta["filas"]:
                f["valores"] = revisadas[f["id"]]
            meta["resumen_revision"] += " El Excel revisado quedó guardado. " + ("Elige el factor para completar los precios vacíos." if factores_pendientes else "Completa los precios pendientes y adjunta esta nueva versión del Excel.")
            _guardar(meta)
            _copiar_version(meta)
            return publico(meta)
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
        meta.update(version=meta["version"] + 1, pendientes=[], factores_pendientes=[], factores_elegidos=factores)
        meta["resumen_revision"] += " Líneas y precios validados; los TXT de comas y tabulaciones están listos."
        _guardar(meta)
        if propagar:
            _propagar_correcciones(meta, datos, uid)
        return publico(meta)


def _propagar_correcciones(meta, datos, uid):
    """Propaga filas verificadas a reportes del mismo lote, sin perder otros pendientes."""
    cols = meta["columnas"]
    clave_idx = cols.index("Clave Artículo")
    mapa = {str(f[clave_idx]): f for f in datos}
    for archivo in directorio().glob("*.json"):
        otro = json.loads(archivo.read_text(encoding="utf-8"))
        if (otro["id"] == meta["id"] or not otro["pendientes"] or
            otro.get("lote_id") != meta.get("lote_id") or otro["columnas"] != cols or
            otro.get("estado") == "factor_pendiente"):
            continue
        compatibles = {}
        for f in otro["filas"]:
            clave = str(f["valores"][clave_idx])
            if clave not in mapa:
                continue
            editable = clave in otro.get("lineas_editables", [])
            if all(str(f["valores"][c] or "") == str(mapa[clave][c] or "") for c, nombre in enumerate(cols)
                   if nombre not in PRECIOS and not (nombre == "Línea" and editable)):
                compatibles[clave] = mapa[clave]
        if not compatibles:
            continue
        wb = openpyxl.load_workbook(directorio() / (otro["id"] + ".xlsx"))
        originales = {f["id"]: f for f in otro["filas"]}
        for r in range(2, wb.active.max_row + 1):
            f = originales[wb.active.cell(r, len(cols) + 1).value]
            clave = str(f["valores"][clave_idx])
            if clave not in compatibles:
                continue
            for c, nombre in enumerate(cols, 1):
                if nombre in PRECIOS or (nombre == "Línea" and clave in otro.get("lineas_editables", [])):
                    wb.active.cell(r, c).value = compatibles[clave][c - 1]
                    from openpyxl.comments import Comment
                    from app.services.almacen.procedencia import explicar_producto
                    texto = explicar_producto(clave, meta.get("meta_por_clave", {}).get(clave, {}))
                    wb.active.cell(r, c).comment = Comment(texto or "Corrección verificada del mismo lote de reportes.", "Flucito")
        contenido = io.BytesIO()
        wb.save(contenido)
        try:
            validar_corregido(otro["id"], contenido.getvalue(), uid, propagar=False,
                             factores_elegidos=meta.get("factores_elegidos"))
        except HTTPException as exc:
            # Un consolidado puede contener filas de otros proveedores todavía
            # pendientes. Guardar la corrección parcial exige nueva versión.
            restantes = [p for p in otro["pendientes"] if p["producto"] not in compatibles]
            if exc.status_code != 422 or not restantes:
                continue
            with _LOCK, bloquear_reporte(otro["id"]):
                actual = cargar(otro["id"], uid=uid)
                if actual["version"] != otro["version"] or actual["estado"] == "validado":
                    continue
                for f in otro["filas"]:
                    clave = str(f["valores"][clave_idx])
                    if clave in compatibles:
                        f["valores"] = compatibles[clave]
                        otro.setdefault("meta_por_clave", {})[clave] = meta.get("meta_por_clave", {}).get(clave, {})
                otro.update(version=otro["version"] + 1, pendientes=restantes,
                    resumen_revision=f"Reporte {otro['nombre']}: se actualizaron {', '.join(compatibles)} desde la revisión del mismo lote. Las demás filas siguen pendientes.")
                otro["lineas_editables"] = [c for c in otro.get("lineas_editables", []) if c not in compatibles]
                wb["_FLUCITO"].cell(1, 2, otro["version"])
                stage = directorio() / (otro["id"] + ".parcial.xlsx")
                wb.save(stage)
                os.replace(stage, directorio() / (otro["id"] + ".xlsx"))
                _guardar(otro)
                _copiar_version(otro)
