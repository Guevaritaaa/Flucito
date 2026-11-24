"""Preguntas tipadas, borradores persistentes y continuación directa de herramientas."""
from __future__ import annotations

import hashlib
import json
import math
import uuid
from copy import deepcopy

from fastapi import HTTPException
from sqlalchemy import select, update

from app.core.database import Base, SessionLocal, engine
from app.models.conversacion import ConfirmacionPendiente, Conversacion
from app.models.preferencia import PreferenciaDecision
from app.schemas.decisiones import EnvioDecisiones
from app.services.contexto_decisiones import contexto

PRECIOS = ("PUBLICO", "MINIMO", "MOSTRADOR", "MAYOREO", "DISTRIBUIDOR")
MANUAL = "LLENADO_MANUAL"


def validar_factor(datos):
    """Convierte pasos guiados a plantillas; ninguna expresión proviene del cliente."""
    nombre = str(datos.get("nombre", "")).strip()
    if not nombre or len(nombre) > 80:
        raise ValueError("Escribe un nombre de factor de hasta 80 caracteres.")
    formulas = {}
    for precio in PRECIOS:
        fila = datos.get("precios", {}).get(precio, {})
        base = fila.get("base", "COSTEO")
        if base not in {"COSTEO", "PUBLICO"} or (precio == "PUBLICO" and base != "COSTEO"):
            raise ValueError(f"Base inválida para {precio}.")
        expresion = "{" + base + "}"
        pasos = fila.get("pasos", [])
        if not isinstance(pasos, list) or len(pasos) > 12:
            raise ValueError("Cada precio admite hasta 12 pasos.")
        for paso in pasos:
            valor = paso.get("valor")
            if isinstance(valor, bool):
                raise ValueError("Los factores deben ser numéricos.")
            valor = float(valor)
            if not math.isfinite(valor) or valor <= 0 or paso.get("operacion") not in {"*", "/"}:
                raise ValueError("Usa multiplicaciones o divisiones con valores positivos y finitos.")
            expresion = f"({expresion}{paso['operacion']}{valor!r})"
        formulas[precio] = expresion
    from app.services.almacen.factores import evaluar_aritmetica
    publico = evaluar_aritmetica(formulas["PUBLICO"], 100, 0)
    if any(not math.isfinite(evaluar_aritmetica(f, 100, publico)) or evaluar_aritmetica(f, 100, publico) <= 0 for f in formulas.values()):
        raise ValueError("El factor produce precios inválidos.")
    return "CUSTOM:" + json.dumps({"nombre": nombre, "formulas": formulas}, separators=(",", ":"))


def clave_preferencia(tipo, contexto_pregunta):
    texto = json.dumps([tipo, contexto_pregunta], sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(texto.encode()).hexdigest()


def opcion(id, titulo, descripcion):
    return {"id": id, "titulo": titulo, "descripcion": descripcion}


def construir(datos, herramienta, argumentos, uid):
    from app.services.almacen.factores import CATALOGO_FACTORES
    preguntas = []

    def agregar(id, tipo, titulo, opciones, ctx=None, **extra):
        preguntas.append({"id": id, "tipo": tipo, "titulo": titulo, "opciones": opciones,
                          "contexto": ctx or {}, "clave_preferencia": clave_preferencia(tipo, ctx) if tipo in {"factor", "metros", "unidad"} else None, **extra})

    for linea in datos.get("lineas_sin_factor", []):
        codigo = str(linea["linea"])
        agregar("factor:" + codigo, "factor", f"¿Qué factor deseas aplicar a {codigo} ({linea.get('descripcion', '')})?",
                [opcion(k, k, " · ".join(f"{p}: {v}" for p, v in fs.items())) for k, fs in CATALOGO_FACTORES.items()] +
                [opcion("custom", "Crear factor personalizado", "Define los cinco precios en una tabla guiada."),
                 opcion("manual", "Dejar precios de venta para llenado manual", "Los cinco precios de venta quedarán vacíos; el TXT esperará su corrección.")], {"linea": codigo}, costo_ejemplo=100)
    for producto in datos.get("productos_sin_linea", []):
        clave = str(producto["clave_articulo"])
        opciones = []
        for grupo in producto.get("sugerencias", []):
            from app.services.almacen.factores import resolver_linea
            factor = resolver_linea(grupo["linea"])["factor"]
            referencias = grupo["referencias"]
            opciones.append(opcion("linea:" + grupo["linea"], "Aplicar línea " + grupo["linea"],
                "; ".join(f"{r['cve_art']} — {r['descr']} · línea {r['linea']}" for r in referencias)
                + f". Factor: {factor or 'se preguntará a continuación'}. Son referencias similares; conserva las diferencias de modelo y medida."))
        opciones.append(opcion("manual", "Completar línea y precios en el Excel",
            "Se conserva el costo de compra. La línea y los cinco precios de venta quedan vacíos; los TXT esperan la revisión."))
        agregar("linea:" + clave, "linea", f"{clave}: confirma la línea del producto", opciones,
                {"producto": clave}, explicacion=producto.get("explicacion"), sugerencias=producto.get("sugerencias", []))
    for rollo in datos.get("rollos_pendientes", []):
        clave = str(rollo["clave_articulo"])
        ctx = {"producto": clave, "unidad": rollo.get("clave_unidad"), "metros": rollo.get("metros")}
        if rollo.get("es_xro"):
            agregar("unidad:" + clave, "unidad", f"{clave}: ¿qué unidad deseas usar?", [
                opcion("conservar", "Conservar XRO", "La unidad seguirá siendo rollo."),
                opcion("mtr", "Cambiar a MTR", "La clave de unidad del reporte será metros; no cambia por sí sola el precio.")], ctx)
        metros = rollo.get("metros")
        precio = rollo.get("precio_compra_bruto", 0)
        opciones = [opcion("conservar", "Conservar precio original", f"Se conservará el precio de compra {precio}; no se dividirá.")]
        if metros:
            opciones.append(opcion("dividir", "Dividir precio entre los metros", f"{precio} ÷ {metros} = {float(precio) / float(metros):.4f} por metro."))
        opciones.append(opcion("manual", "Dejar precios para llenado manual", "Conserva la unidad original y deja compra y los cinco precios de venta vacíos; el TXT queda pendiente."))
        agregar("metros:" + clave, "metros", f"{clave}: {rollo.get('descripcion', '')}", opciones, ctx)
    if datos.get("tipo_confirmacion") == "solo_xml":
        agregar("documentos", "documentos", "Hay facturas sin PDF o TXT de apoyo. ¿Cómo deseas continuar?", [
            opcion("procesar", "Procesar con el XML", "Usa los datos del XML; conserva los avisos por información faltante."),
            opcion("omitir", "Procesar solo las completas", "Las facturas sin documentos de apoyo quedan pendientes."),
            opcion("cancelar", "Cancelar operación", "No se generará el reporte de esta solicitud.")])
    candidatos = datos.get("candidatos", [])
    if candidatos:
        agregar("candidato", "seleccion", datos.get("mensaje", "Selecciona el elemento correcto"),
                [opcion(str(c["id"]), c.get("ruta_completa", c.get("nombre", c["id"])), "Se utilizará únicamente este elemento.") for c in candidatos], parametro=datos.get("parametro", "ruta_origen"), ruta_ambigua=datos.get("ruta_ambigua"))
    elif datos.get("requiere_confirmacion") and not preguntas:
        if herramienta == "gestionar_archivos_drive" and argumentos.get("accion") == "eliminar_elemento":
            agregar("autorizar", "aprobacion", datos.get("mensaje", "¿Autorizar eliminación?"), [
                opcion("autorizar", "Enviar a la papelera", "Se enviará la carpeta indicada y su contenido a la papelera de Drive."),
                opcion("cancelar", "Cancelar", "Se conservarán la carpeta y su contenido.")])
        else:
            agregar("destino", "destino", datos.get("mensaje", "Selecciona otra ubicación para continuar"), [
                opcion("otra_ruta", "Usar otra carpeta", "Indica la ruta completa o id:ID de una carpeta existente; se validará antes de continuar."),
                opcion("cancelar", "Cancelar", "No se continuará con esta operación.")])
    if not preguntas:
        return None
    respuestas = {}
    if uid is not None:
        with SessionLocal() as db:
            for p in preguntas:
                if p["clave_preferencia"]:
                    pref = db.scalar(select(PreferenciaDecision).where(PreferenciaDecision.usuario_id == uid, PreferenciaDecision.clave == p["clave_preferencia"]))
                    if pref:
                        respuestas[p["id"]] = json.loads(pref.respuesta_json)
                        p["recordada"] = True
    for p in preguntas:
        if p["tipo"] == "metros" and respuestas.get(p["id"], {}).get("opcion") == "manual":
            unidad = "unidad:" + p["contexto"]["producto"]
            if any(q["id"] == unidad for q in preguntas):
                respuestas[unidad] = {"opcion": "conservar", "recordar": False, "campos": {}}
    return {"id": uuid.uuid4().hex, "revision": 1, "estado": "pendiente", "preguntas": preguntas,
            "respuestas": respuestas, "permite_recordar": uid is not None}


def verificar_dueno(db, sid, uid):
    conv = db.get(Conversacion, sid)
    if conv and conv.usuario_id != uid:
        raise HTTPException(403, "Esta conversación pertenece a otro usuario.")
    return conv


def leer(sid, uid):
    with SessionLocal() as db:
        verificar_dueno(db, sid, uid)
        fila = db.scalar(select(ConfirmacionPendiente).where(ConfirmacionPendiente.conversacion_id == sid))
        return json.loads(fila.datos_json) if fila else None


def registrar(sid, uid, datos, herramienta, argumentos, anteriores=None):
    Base.metadata.create_all(engine)
    continuacion = datos.get("continuacion", {})
    if continuacion.get("herramienta") == "gestionar_archivos_drive":
        herramienta, argumentos = continuacion["herramienta"], continuacion["argumentos"]
    interaccion = construir(datos, herramienta, argumentos, uid)
    if interaccion is None:
        return None
    if anteriores:
        interaccion["anteriores"] = anteriores
        if herramienta == "generar_entradas_almacen":
            # La prevalidación puede descubrir factores después de autorizar XML.
            # Conserva todas las respuestas editables hasta generar el reporte.
            preguntas_previas = {p["id"]: p for a in anteriores for p in a["preguntas"]}
            respuestas_previas = {k: v for a in anteriores for k, v in a["respuestas"].items()}
            preguntas_previas.update({p["id"]: p for p in interaccion["preguntas"]})
            interaccion["preguntas"] = list(preguntas_previas.values())
            interaccion["respuestas"] = {**respuestas_previas, **interaccion["respuestas"]}
    estado = {"interaccion": interaccion, "herramienta": herramienta, "argumentos": argumentos, "observado": datos}
    with SessionLocal() as db:
        conv = verificar_dueno(db, sid, uid)
        if conv is None:
            db.add(Conversacion(id=sid, usuario_id=uid, titulo="Decisiones de Flucito"))
            db.flush()
        fila = db.scalar(select(ConfirmacionPendiente).where(ConfirmacionPendiente.conversacion_id == sid))
        if fila:
            fila.datos_json = json.dumps(estado, ensure_ascii=False)
        else:
            db.add(ConfirmacionPendiente(conversacion_id=sid, usuario_id=uid, datos_json=json.dumps(estado, ensure_ascii=False)))
        db.commit()
    return interaccion


def validar_respuestas(interaccion, respuestas, completas=False):
    preguntas = {p["id"]: p for p in interaccion["preguntas"]}
    if set(respuestas) - preguntas.keys():
        raise ValueError("La respuesta contiene preguntas desconocidas.")
    if completas and set(respuestas) != preguntas.keys():
        raise ValueError("Responde todas las preguntas antes de aplicar las decisiones.")
    for id, respuesta in respuestas.items():
        p = preguntas[id]
        if respuesta["opcion"] not in {o["id"] for o in p["opciones"]}:
            raise ValueError("Selecciona una opción disponible.")
        if respuesta.get("recordar") and (not p["clave_preferencia"] or not interaccion["permite_recordar"]):
            raise ValueError("Esta elección no se puede recordar.")
        if completas and respuesta["opcion"] == "custom":
            validar_factor(respuesta.get("campos", {}))
        if completas and respuesta["opcion"] == "otra_ruta" and not str(respuesta.get("campos", {}).get("ruta", "")).strip():
            raise ValueError("Indica la ruta de la carpeta.")
        if completas and p["tipo"] == "metros" and respuesta["opcion"] == "manual":
            unidad = respuestas.get("unidad:" + p["contexto"]["producto"], {})
            if unidad.get("opcion") == "mtr":
                raise ValueError("El llenado manual debe conservar la unidad original.")


def guardar_envio(sid, uid, envio: EnvioDecisiones):
    """CAS sobre el documento completo: funciona también con varios procesos."""
    with SessionLocal() as db:
        verificar_dueno(db, sid, uid)
        fila = db.scalar(select(ConfirmacionPendiente).where(ConfirmacionPendiente.conversacion_id == sid))
        if not fila:
            raise HTTPException(404, "La pregunta ya no está disponible.")
        original = fila.datos_json
        estado = json.loads(original)
        i = estado["interaccion"]
        if i["id"] != envio.interaccion_id or i["revision"] != envio.revision or i["estado"] != "pendiente":
            raise HTTPException(409, "Esta pregunta cambió o ya fue enviada. Recarga la conversación.")
        respuestas = {k: v.model_dump() for k, v in envio.respuestas.items()}
        try:
            validar_respuestas(i, respuestas, envio.accion == "confirmar")
        except (ValueError, TypeError, OverflowError) as exc:
            raise HTTPException(422, str(exc)) from exc
        i["respuestas"] = respuestas
        i["revision"] += 1
        i["estado"] = {"borrador": "pendiente", "confirmar": "ejecutando", "cancelar": "cancelada"}[envio.accion]
        cambio = db.execute(update(ConfirmacionPendiente).where(ConfirmacionPendiente.id == fila.id, ConfirmacionPendiente.datos_json == original).values(datos_json=json.dumps(estado, ensure_ascii=False)))
        if cambio.rowcount != 1:
            db.rollback()
            raise HTTPException(409, "Otra solicitud modificó estas decisiones.")
        if uid is not None and envio.accion == "confirmar" and not any(r["opcion"] == "cancelar" for r in respuestas.values()):
            _guardar_preferencias(db, uid, i)
        db.commit()
    return estado


def traducir(estado):
    args = {k: deepcopy(v) for k, v in estado["argumentos"].items() if v is not None}
    cancelado = False
    i = estado["interaccion"]
    for p in i["preguntas"]:
        r = i["respuestas"][p["id"]]
        valor, campos = r["opcion"], r.get("campos", {})
        cancelado |= valor == "cancelar"
        if p["tipo"] == "factor":
            args.setdefault("factores_elegidos", {})[p["contexto"]["linea"]] = validar_factor(campos) if valor == "custom" else MANUAL if valor == "manual" else valor
            args["guardar_factores"] = False
        elif p["tipo"] == "linea":
            d = {"manual": True}
            if valor != "manual":
                linea = valor.removeprefix("linea:")
                grupo = next(g for g in p["sugerencias"] if g["linea"] == linea)
                d = {"linea": linea, "referencia": grupo["referencias"][0]["cve_art"], "confirmada": True}
            args.setdefault("decisiones_lineas", {})[p["contexto"]["producto"]] = d
        elif p["tipo"] in {"unidad", "metros"}:
            d = args.setdefault("decisiones_rollos", {}).setdefault(p["contexto"]["producto"], {})
            if p["tipo"] == "unidad":
                d["cambiar_a_mtr"] = valor == "mtr"
            else:
                d.update(dividir_entre_metros=valor == "dividir", manual=valor == "manual")
                if valor == "manual":
                    d["cambiar_a_mtr"] = False
        elif p["tipo"] == "documentos":
            args.update(confirmar_solo_xml=valor == "procesar", omitir_incompletas=valor == "omitir")
        elif p["tipo"] == "aprobacion":
            args["confirmar_eliminar_con_contenido"] = valor == "autorizar"
        elif p["tipo"] == "seleccion":
            args[p.get("parametro", "ruta_origen")] = "id:" + valor
            if args.get("rutas_origen"):
                ambigua = p.get("ruta_ambigua")
                if ambigua not in args["rutas_origen"]:
                    raise ValueError("No se pudo identificar la ruta ambigua de la selección.")
                args["rutas_origen"] = ["id:" + valor if r == ambigua else r for r in args["rutas_origen"]]
        elif p["tipo"] == "destino" and valor == "otra_ruta":
            args["ruta_destino"] = str(campos["ruta"]).strip()
    return args, cancelado


def _guardar_preferencias(db, uid, i):
    for p in i["preguntas"]:
        clave = p["clave_preferencia"]
        if not clave:
            continue
        r = i["respuestas"][p["id"]]
        pref = db.scalar(select(PreferenciaDecision).where(PreferenciaDecision.usuario_id == uid, PreferenciaDecision.clave == clave))
        if r.get("recordar"):
            if not pref:
                pref = PreferenciaDecision(usuario_id=uid, clave=clave, respuesta_json="{}")
                db.add(pref)
            pref.respuesta_json = json.dumps(r, ensure_ascii=False)
        elif pref:
            db.delete(pref)


def finalizar(sid, uid, estado, resultado, error=False):
    estado["interaccion"]["estado"] = "error" if error else "aplicada"
    with SessionLocal() as db:
        fila = db.scalar(select(ConfirmacionPendiente).where(ConfirmacionPendiente.conversacion_id == sid))
        if fila:
            fila.datos_json = json.dumps(estado, ensure_ascii=False)
            db.commit()


def revalidar_aprobacion(estado, args):
    """La autorización de papelera corresponde a un objetivo y contenido concretos."""
    observado = estado.get("observado", {})
    if estado["herramienta"] != "gestionar_archivos_drive" or args.get("accion") != "eliminar_elemento" or not observado.get("objetivo_id"):
        return None
    from app.core.config import settings
    from app.services.almacen.fuentes.google_drive_client import crear_cliente_drive, _listar_hijos
    from app.services.almacen.fuentes.navegador_drive import resolver_para_movimiento
    cliente = crear_cliente_drive()
    objetivo = resolver_para_movimiento(cliente, "id:" + observado["objetivo_id"], settings.google_drive_folder_id)
    hijos = _listar_hijos(cliente, objetivo["id"])
    ids = sorted(str(a.get("id", "")) for a in hijos)
    args["ruta_origen"] = "id:" + objetivo["id"]
    if objetivo["ruta_completa"] != observado.get("ruta_objetivo") or ids != observado.get("contenido_ids"):
        return {**observado, "ruta_objetivo": objetivo["ruta_completa"], "contenido_ids": ids,
                "archivos_encontrados": sorted(a.get("name", "") for a in hijos), "total_elementos_internos": len(hijos),
                "requiere_confirmacion": True, "mensaje": "La carpeta o su contenido cambiaron. Revisa de nuevo antes de enviar a la papelera: " + ", ".join(a.get("name", "") for a in hijos)}
    return None


def respuesta_textual(estado, texto):
    """Interpretación conservadora: un sí/no nunca decide varias preguntas."""
    i = deepcopy(estado["interaccion"])
    import re
    import unicodedata
    def normalizar(t):
        return "".join(c for c in unicodedata.normalize("NFD", str(t).casefold()) if unicodedata.category(c) != "Mn").strip().rstrip(".! ")
    texto = normalizar(texto)
    dirigidas = [p for p in i["preguntas"] if any(v is not None and len(str(v)) > 2 and re.search(r"(?<!\w)" + re.escape(normalizar(v)) + r"(?!\w)", texto) for k, v in p["contexto"].items() if k in {"linea", "producto"})]
    pendientes = dirigidas or [p for p in i["preguntas"] if p["id"] not in i["respuestas"]]
    coincidencias = []
    for p in pendientes:
        for n, o in enumerate(p["opciones"], 1):
            titulo, id = normalizar(o["titulo"]), normalizar(o["id"])
            if texto in {id, titulo} or titulo in texto or (p["tipo"] == "factor" and len(id) > 2 and re.search(r"(?<!\w)" + re.escape(id) + r"(?!\w)", texto)) or (len(pendientes) == 1 and texto == str(n)):
                coincidencias.append((p, o))
        if p["tipo"] == "metros" and not coincidencias:
            valor = None
            if re.search(r"\b(no\s+divid\w*|conserv\w*|dej\w*\s+(?:el\s+)?precio\s+(?:igual|original))\b", texto):
                valor = "conservar"
            elif re.search(r"\b(divid\w*|divis\w*)\b", texto):
                valor = "dividir"
            elif re.search(r"\b(manual|vacios?|blanco)\b", texto):
                valor = "manual"
            coincidencias.extend((p, o) for o in p["opciones"] if o["id"] == valor)
    if len(pendientes) == 1 and texto in {"s", "si", "sí", "y", "n", "no"}:
        p = pendientes[0]
        si = texto in {"s", "si", "sí", "y"}
        id = {"unidad": "mtr" if si else "conservar", "metros": "dividir" if si else "conservar", "aprobacion": "autorizar" if si else "cancelar", "documentos": "procesar" if si else "cancelar"}.get(p["tipo"])
        coincidencias = [(p, o) for o in p["opciones"] if o["id"] == id]
    if len(coincidencias) != 1:
        return None
    p, o = coincidencias[0]
    i["respuestas"][p["id"]] = {"opcion": o["id"], "recordar": False, "campos": {}}
    if p["tipo"] == "metros" and o["id"] == "manual":
        unidad = "unidad:" + p["contexto"]["producto"]
        if any(q["id"] == unidad for q in i["preguntas"]):
            i["respuestas"][unidad] = {"opcion": "conservar", "recordar": False, "campos": {}}
    return EnvioDecisiones(interaccion_id=i["id"], revision=i["revision"], respuestas=i["respuestas"], accion="borrador")
