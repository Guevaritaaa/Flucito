import io
import json
from copy import deepcopy

import openpyxl
import pandas as pd
import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.schemas.decisiones import EnvioDecisiones
from app.services import decisiones as d
from app.services import revision_reportes as rr
from app.services.almacen import excel, factores
from app.services.contexto_decisiones import contexto


@pytest.fixture
def entorno(monkeypatch, tmp_path):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(d, "engine", engine)
    monkeypatch.setattr(d, "SessionLocal", session)
    monkeypatch.setattr(excel, "CARPETA_DATOS", tmp_path)
    from app.api.v1.routes import chat
    monkeypatch.setattr(chat, "engine", engine)
    monkeypatch.setattr(chat, "SessionLocal", session)
    monkeypatch.setattr(chat, "CARPETA_DATOS", tmp_path)
    token = contexto.set({"session_id": "chat-uno", "usuario_id": None})
    yield tmp_path, session
    contexto.reset(token)
    engine.dispose()


def datos_preguntas():
    return {"requiere_confirmacion": True, "lineas_sin_factor": [{"linea": "DAYCO", "descripcion": "Bandas"}],
            "rollos_pendientes": [{"clave_articulo": "MANG-1", "es_xro": True, "clave_unidad": "XRO", "metros": 20, "precio_compra_bruto": 600, "descripcion": "Manguera"}]}


def envio(i, respuestas, accion="borrador"):
    return EnvioDecisiones(interaccion_id=i["id"], revision=i["revision"], respuestas=respuestas, accion=accion)


def respuestas(i):
    return {p["id"]: {"opcion": p["opciones"][0]["id"], "recordar": False, "campos": {}} for p in i["preguntas"]}


def test_borrador_persistente_aislado_revision_y_confirmacion_unica(entorno):
    i = d.registrar("chat-uno", None, datos_preguntas(), "generar_entradas_almacen", {"factores_elegidos": None, "decisiones_rollos": None})
    assert [p["tipo"] for p in i["preguntas"] if "MANG-1 — Manguera" in p["titulo"]] == ["unidad", "metros"]
    r = respuestas(i)
    guardado = d.guardar_envio("chat-uno", None, envio(i, r))
    assert d.leer("chat-uno", None) == guardado
    assert d.leer("otra-conversacion", None) is None
    with pytest.raises(HTTPException) as e:
        d.guardar_envio("chat-uno", None, envio(i, r))
    assert e.value.status_code == 409
    confirmado = d.guardar_envio("chat-uno", None, envio(guardado["interaccion"], r, "confirmar"))
    args, cancelado = d.traducir(confirmado)
    assert args["guardar_factores"] is False
    assert args["factores_elegidos"]["DAYCO"] == "COMPRAS GENERALES LOCALES"
    assert not cancelado
    with pytest.raises(HTTPException):
        d.guardar_envio("chat-uno", None, envio(guardado["interaccion"], r, "confirmar"))


def test_preferencias_personales_y_contexto_equivalente(entorno):
    _, session = entorno
    from app.models.usuario import Usuario
    with session() as db:
        for n in (1, 2):
            db.add(Usuario(id=n, username=f"u{n}", nombre_completo="Operador", password_hash="prueba"))
        db.commit()
    i = d.registrar("usuario-1", 1, datos_preguntas(), "generar_entradas_almacen", {})
    r = respuestas(i)
    for valor in r.values():
        valor["recordar"] = True
    estado = d.guardar_envio("usuario-1", 1, envio(i, r, "confirmar"))
    d.finalizar("usuario-1", 1, estado, {})
    mismo = d.construir(datos_preguntas(), "generar_entradas_almacen", {}, 1)
    assert len(mismo["respuestas"]) == 3
    assert d.construir(datos_preguntas(), "generar_entradas_almacen", {}, 2)["respuestas"] == {}
    diferentes = datos_preguntas()
    diferentes["rollos_pendientes"][0]["metros"] = 30
    assert set(d.construir(diferentes, "generar_entradas_almacen", {}, 1)["respuestas"]) == {"factor:DAYCO"}
    with pytest.raises(HTTPException) as e:
        d.leer("usuario-1", 2)
    assert e.value.status_code == 403
    for valor in r.values():
        valor["recordar"] = False
    nuevo = d.registrar("usuario-1", 1, datos_preguntas(), "generar_entradas_almacen", {})
    estado = d.guardar_envio("usuario-1", 1, envio(nuevo, r, "confirmar"))
    d.finalizar("usuario-1", 1, estado, {})
    assert d.construir(datos_preguntas(), "generar_entradas_almacen", {}, 1)["respuestas"] == {}


def factor_guiado():
    return {"nombre": "Factor propio", "precios": {p: {"base": "COSTEO" if p == "PUBLICO" else "PUBLICO", "pasos": [{"operacion": "/", "valor": .8}, {"operacion": "*", "valor": 2}]} for p in d.PRECIOS}}


def test_factor_guiado_numeros_formulas_y_validacion():
    datos = factor_guiado()
    factor = d.validar_factor(datos)
    assert factores.normalizar_eleccion_factor(factor) == factor
    precios = factores.calcular_precios_numericos(factor, 100)
    assert precios["PUBLICO"] == 250
    assert precios["MINIMO"] == 625
    formulas = factores.generar_formulas_fila(factor, 2)
    assert "S2" in formulas["PUBLICO"] and "T2" in formulas["MINIMO"]
    datos["precios"]["PUBLICO"]["pasos"][0]["valor"] = 0
    with pytest.raises(ValueError):
        d.validar_factor(datos)
    with pytest.raises(ValueError):
        factores.evaluar_aritmetica("__import__('os').getcwd()", 1)


def test_respuesta_ambigua_no_decide_varias_preguntas(entorno):
    i = d.registrar("chat-uno", None, datos_preguntas(), "generar_entradas_almacen", {})
    assert d.respuesta_textual({"interaccion": i}, "sí") is None
    i["preguntas"] = [p for p in i["preguntas"] if p["tipo"] == "metros"]
    envio_texto = d.respuesta_textual({"interaccion": i}, "sí")
    assert envio_texto.accion == "borrador"
    assert envio_texto.respuestas["metros:MANG-1"].opcion == "dividir"


def crear_reporte(entorno, nombre="BASE_ENTRADAS_ALMACEN"):
    ruta, _ = entorno
    fila = {c: 0 for c in excel.COLUMNAS_ASPEL}
    fila.update({"Clave Artículo": "MANG-1", "DESCRIPCION": "Manguera", "Línea": "DAYCO", "Clave unidad": "XRO", "PRECIO COMPRA": None})
    for p in d.PRECIOS:
        fila[p] = None
    df = pd.DataFrame([fila], columns=excel.COLUMNAS_ASPEL)
    df.attrs["meta_por_clave"] = {"MANG-1": {"manual": True}}
    archivo = excel.guardar_en_base_acumulada(df, str(ruta), prefijo=nombre)
    revision = rr.revision_actual(archivo, "chat-uno", None)
    return archivo, revision


def corregir(archivo):
    wb = openpyxl.load_workbook(archivo)
    ws = wb.active
    for c in ws[1]:
        if c.value in rr.PRECIOS:
            ws.cell(2, c.column, 123.45)
    return wb


def bytes_libro(wb):
    salida = io.BytesIO()
    wb.save(salida)
    return salida.getvalue()


def test_vacios_reales_bloqueo_txt_validacion_y_version(entorno):
    archivo, revision = crear_reporte(entorno)
    assert revision["pendientes"][0]["producto"] == "MANG-1"
    assert not (entorno[0] / "BASE_ENTRADAS_ALMACEN_COMAS.txt").exists()
    with pytest.raises(HTTPException) as e:
        rr.verificar_txt(archivo, None)
    assert e.value.status_code == 409
    contenido = bytes_libro(corregir(archivo))
    resultado = rr.validar_corregido(revision["id"], contenido, None)
    assert resultado["version"] == 2 and resultado["pendientes"] == []
    rr.verificar_txt(archivo, None)
    assert "123.45" in (entorno[0] / "BASE_ENTRADAS_ALMACEN_COMAS.txt").read_text()
    with pytest.raises(HTTPException):
        rr.validar_corregido(revision["id"], contenido, None)


@pytest.mark.parametrize("alteracion", ["producto", "fila", "vacio", "formula", "version"])
def test_rechaza_excel_alterado_sin_modificar_original(entorno, alteracion):
    archivo, revision = crear_reporte(entorno)
    original = open(archivo, "rb").read()
    wb = corregir(archivo)
    ws = wb.active
    columnas = {c.value: c.column for c in ws[1]}
    if alteracion == "producto":
        ws.cell(2, columnas["Clave Artículo"], "OTRO")
    elif alteracion == "fila":
        ws.delete_rows(2)
    elif alteracion == "vacio":
        ws.cell(2, columnas["PUBLICO"]).value = None
    elif alteracion == "formula":
        ws.cell(2, columnas["PUBLICO"], "=HYPERLINK(\"http://example.com\")")
    else:
        wb["_FLUCITO"].cell(1, 2, 999)
    with pytest.raises(HTTPException) as e:
        rr.validar_corregido(revision["id"], bytes_libro(wb), None)
    assert e.value.status_code == 422
    assert open(archivo, "rb").read() == original
    assert rr.cargar(revision["id"], "chat-uno", None)["pendientes"]


def test_actualiza_reportes_asociados_del_mismo_lote(entorno):
    mini, rm = crear_reporte(entorno, "ENTRADAS_PROVEEDOR")
    archivo, revision = crear_reporte(entorno)
    rr.validar_corregido(revision["id"], bytes_libro(corregir(archivo)), None)
    assert rr.cargar(rm["id"], "chat-uno", None)["estado"] == "validado"
    assert openpyxl.load_workbook(mini).active.cell(2, excel.COLUMNAS_ASPEL.index("PUBLICO") + 1).value == 123.45


def test_continuacion_directa_sin_modelo_y_cancelacion(entorno, monkeypatch):
    from app.api.v1.routes import chat
    from app.agents import tools
    from app.schemas.chat import ChatRequest
    llamadas = []
    class Herramienta:
        name = "generar_entradas_almacen"
        def invoke(self, args, **kwargs):
            llamadas.append(args)
            return json.dumps({"ok": True, "reporte_generado": True})
    monkeypatch.setattr(tools, "HERRAMIENTAS", [Herramienta()])
    monkeypatch.setattr(chat, "_ejecutar_chat_impl", lambda *a: pytest.fail("No debe invocar al modelo"))
    i = d.registrar("chat-uno", None, datos_preguntas(), "generar_entradas_almacen", {"factores_elegidos": None})
    resultado = chat._ejecutar_chat(ChatRequest(session_id="chat-uno", mensaje="Confirmar", decisiones=envio(i, respuestas(i), "confirmar")))
    assert resultado.interaccion["estado"] == "aplicada"
    assert d.leer("chat-uno", None)["interaccion"]["estado"] == "aplicada"
    assert len(llamadas) == 1
    with pytest.raises(HTTPException):
        chat._ejecutar_chat(ChatRequest(session_id="chat-uno", mensaje="Confirmar", decisiones=envio(i, respuestas(i), "confirmar")))
    assert len(llamadas) == 1
    i = d.registrar("chat-uno", None, datos_preguntas(), "generar_entradas_almacen", {})
    resultado = chat._ejecutar_chat(ChatRequest(session_id="chat-uno", mensaje="Cancelar", decisiones=envio(i, {}, "cancelar")))
    assert resultado.interaccion["estado"] == "cancelada" and len(llamadas) == 1


def test_lenguaje_natural_puede_cambiar_una_respuesta_previa(entorno):
    i = d.construir(datos_preguntas(), "generar_entradas_almacen", {}, None)
    i["respuestas"] = respuestas(i)
    cambio = d.respuesta_textual({"interaccion": i}, "Para DAYCO quiero aplicar FESTO")
    assert cambio.respuestas["factor:DAYCO"].opcion == "FESTO"
    cambio = d.respuesta_textual({"interaccion": i}, "Divide el precio de MANG-1 entre los metros")
    assert cambio.respuestas["metros:MANG-1"].opcion == "dividir"


def test_continuacion_pide_solo_decisiones_pendientes_y_conserva_las_aplicadas(entorno, monkeypatch):
    from app.agents import tools
    from app.api.v1.routes import chat
    from app.schemas.chat import ChatRequest

    etapas = iter([
        {"ok": True, "requiere_confirmacion": True, "productos_sin_linea": [{
            "clave_articulo": "P1", "descripcion": "Vaso metálico con purga", "sugerencias": [{
                "linea": "ZZ9", "referencias": [{"cve_art": "P2", "descr": "Vaso metálico", "linea": "ZZ9"}],
            }],
        }]},
        {"ok": True, "requiere_confirmacion": True, "lineas_sin_factor": [{"linea": "ZZ9"}]},
        {"ok": True, "reporte_generado": True},
    ])
    llamadas = []

    class Herramienta:
        name = "generar_entradas_almacen"

        def invoke(self, args, **kwargs):
            llamadas.append(args)
            return json.dumps(next(etapas))

    monkeypatch.setattr(tools, "HERRAMIENTAS", [Herramienta()])
    documentos = d.registrar("chat-uno", None, {"tipo_confirmacion": "solo_xml"}, Herramienta.name, {})

    def continuar(interaccion):
        return chat._ejecutar_chat(ChatRequest(session_id="chat-uno", mensaje="Aplicar decisiones y continuar",
            decisiones=envio(interaccion, respuestas(interaccion), "confirmar")))

    linea = continuar(documentos).interaccion
    assert [p["id"] for p in linea["preguntas"]] == ["linea:P1"]
    assert "P1 — Vaso metálico con purga" in linea["preguntas"][0]["titulo"]
    assert linea["preguntas"][0]["opciones"][-1]["titulo"] == "Completar línea y precios manualmente en el Excel"
    assert linea["respuestas"] == {}
    assert linea["anteriores"][0]["respuestas"] == respuestas(documentos)

    factor = continuar(linea).interaccion
    assert [p["id"] for p in factor["preguntas"]] == ["factor:ZZ9"]
    assert [r["id"] for r in factor["anteriores"]] == [documentos["id"], linea["id"]]
    assert all(r["estado"] == "aplicada" for r in factor["anteriores"])
    resultado = continuar(factor)
    assert resultado.interaccion["estado"] == "aplicada"
    assert llamadas[-1]["confirmar_solo_xml"] is True
    assert llamadas[-1]["decisiones_lineas"]["P1"]["linea"] == "ZZ9"
    assert llamadas[-1]["factores_elegidos"]["ZZ9"] == "COMPRAS GENERALES LOCALES"
    assert "Procesar con el XML" in resultado.respuesta
    assert "Aplicar línea ZZ9" in resultado.respuesta


def test_captura_pregunta_real_del_ejecutor_de_herramientas(entorno):
    from langchain_core.messages import AIMessage
    from langchain_core.tools import tool
    from app.agents.ejecucion_tools import ejecutar_herramientas
    @tool
    def generar_entradas_almacen():
        """Herramienta simulada sin efectos externos."""
        return json.dumps(datos_preguntas())
    mensaje = AIMessage(content="", tool_calls=[{"name": generar_entradas_almacen.name, "args": {}, "id": "tool-1", "type": "tool_call"}])
    salida = ejecutar_herramientas({"messages": [mensaje]}, [generar_entradas_almacen])
    assert json.loads(salida["messages"][0].content)["requiere_confirmacion"]
    assert contexto.get()["interaccion"]["preguntas"]
    assert d.leer("chat-uno", None)["herramienta"] == "generar_entradas_almacen"
    segunda = AIMessage(content="", tool_calls=[{"name": generar_entradas_almacen.name, "args": {}, "id": "tool-2", "type": "tool_call"}])
    bloqueada = ejecutar_herramientas({"messages": [mensaje, *salida["messages"], segunda]}, [generar_entradas_almacen])
    assert bloqueada["messages"][0].status == "error"
    assert "pendientes" in bloqueada["messages"][0].content


def test_manual_en_metros_conserva_unidad_y_vacia_seis_precios(entorno, monkeypatch):
    monkeypatch.setattr(excel, "buscar_articulo_sae", lambda *a, **kw: None)
    monkeypatch.setattr(excel, "resolver_proveedor_sae", lambda *a, **kw: (None, "XML"))
    monkeypatch.setattr(excel, "recuperar_clave_truncada", lambda *a, **kw: "M1")
    concepto = {"no_identificacion": "M1", "descripcion": "Manguera rollo 20m", "clave_unidad": "XRO", "valor_unitario": 600, "cantidad": 1, "importe": 600, "clave_prod_serv": "1", "fecha_compra": "2026-11-22", "proveedor_nombre": "Proveedor"}
    fila = excel._fila_desde_concepto(concepto, {"linea": "FESTO"}, decisiones_rollos={"M1": {"manual": True, "cambiar_a_mtr": True}})
    assert fila["Clave unidad"] == "XRO"
    assert all(fila[p] is None for p in rr.PRECIOS)


def test_aprobacion_se_reabre_si_cambia_contenido_drive(entorno, monkeypatch):
    from app.services.almacen.fuentes import google_drive_client as drive
    from app.services.almacen.fuentes import navegador_drive as nav
    monkeypatch.setattr(drive, "crear_cliente_drive", lambda: object())
    monkeypatch.setattr(drive, "_listar_hijos", lambda *a: [{"id": "nuevo", "name": "Factura nueva.xml"}])
    monkeypatch.setattr(nav, "resolver_para_movimiento", lambda *a: {"id": "carpeta", "ruta_completa": "DOCUMENTOS ENTRADA/fecha"})
    estado = {"herramienta": "gestionar_archivos_drive", "observado": {"objetivo_id": "carpeta", "ruta_objetivo": "DOCUMENTOS ENTRADA/fecha", "contenido_ids": ["anterior"]}}
    args = {"accion": "eliminar_elemento", "confirmar_eliminar_con_contenido": True}
    nuevo = d.revalidar_aprobacion(estado, args)
    assert nuevo["requiere_confirmacion"] and nuevo["contenido_ids"] == ["nuevo"]
    assert args["ruta_origen"] == "id:carpeta"


def test_api_rechaza_txt_pendiente_y_acepta_excel_corregido(entorno, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.v1.routes import almacen
    from app.core.security import obtener_usuario_opcional
    _, revision = crear_reporte(entorno)
    monkeypatch.setattr(almacen, "CARPETA_DATOS", entorno[0])
    app = FastAPI()
    app.include_router(almacen.router, prefix="/api/v1")
    app.dependency_overrides[obtener_usuario_opcional] = lambda: None
    client = TestClient(app)
    assert client.get("/api/v1/almacen/download/txt").status_code == 409
    archivo = rr.directorio() / (revision["id"] + ".xlsx")
    contenido = bytes_libro(corregir(archivo))
    ruta = f"/api/v1/almacen/reportes/{revision['id']}"
    assert client.get(ruta + "?session_id=ajena").status_code == 403
    response = client.post(ruta + "/validar?session_id=chat-uno", files={"archivo": ("corregido.xlsx", contenido)})
    assert response.status_code == 200, response.text
    assert client.get(ruta + "/archivo?session_id=chat-uno&formato=tabs").status_code == 200


def test_migracion_preferencias_upgrade_y_downgrade():
    import importlib.util
    from pathlib import Path
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import inspect
    engine = create_engine("sqlite://")
    versiones = Path(__file__).parents[1] / "alembic" / "versions"
    with engine.begin() as conexion:
        with Operations.context(MigrationContext.configure(conexion)):
            for nombre in ("0001_esquema_inicial_flucito.py", "0002_preferencias_decision.py"):
                spec = importlib.util.spec_from_file_location("migracion", versiones / nombre)
                modulo = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(modulo)
                modulo.upgrade()
            assert "preferencias_decision" in inspect(conexion).get_table_names()
            modulo.downgrade()
            assert "preferencias_decision" not in inspect(conexion).get_table_names()
    engine.dispose()


def crear_reporte_linea_pendiente(entorno):
    fila = {c: 0 for c in excel.COLUMNAS_ASPEL}
    fila.update({"Clave Artículo": "PRUEBA-4000D", "DESCRIPCION": "Producto sin línea", "Línea": "", "PRECIO COMPRA": 100})
    for p in d.PRECIOS:
        fila[p] = None
    df = pd.DataFrame([fila], columns=excel.COLUMNAS_ASPEL)
    df.attrs["meta_por_clave"] = {"PRUEBA-4000D": {"manual": True, "linea_pendiente": True, "origen_linea": "SIN_LINEA"}}
    excel.guardar_en_base_acumulada(df, str(entorno[0]), limpiar_previos=True)
    archivo = entorno[0] / excel.NOMBRE_ARCHIVO_BASE
    return archivo, rr.revision_actual(archivo, "chat-uno", None)


@pytest.mark.parametrize("manuales", [0, 2, 5])
def test_excel_linea_existente_completa_solo_precios_vacios(entorno, manuales):
    archivo, revision = crear_reporte_linea_pendiente(entorno)
    wb = openpyxl.load_workbook(archivo)
    ws = wb.active
    cols = {c.value: c.column for c in ws[1]}
    ws.cell(2, cols["Línea"], " ypc ")
    for n, p in enumerate(d.PRECIOS[:manuales]):
        ws.cell(2, cols[p], 800 + n)
    salida = rr.validar_corregido(revision["id"], bytes_libro(wb), None)
    assert salida["estado"] == "validado"
    final = openpyxl.load_workbook(archivo).active
    assert final.cell(2, cols["Línea"]).value == "YPC"
    assert final.cell(2, cols["PRECIO COMPRA"]).value == 100
    calculados = factores.calcular_precios_numericos("YPC", 100)
    for n, p in enumerate(d.PRECIOS):
        assert final.cell(2, cols[p]).value == pytest.approx(800 + n if n < manuales else calculados[p])


@pytest.mark.parametrize("linea", ["ZZ9", "DAYCO"])
def test_excel_linea_sin_factor_conserva_version_y_reanuda(entorno, linea):
    archivo, revision = crear_reporte_linea_pendiente(entorno)
    wb = openpyxl.load_workbook(archivo)
    cols = {c.value: c.column for c in wb.active[1]}
    wb.active.cell(2, cols["Línea"], linea)
    wb.active.cell(2, cols["PUBLICO"], 987.65)
    subido = bytes_libro(wb)
    salida = rr.validar_corregido(revision["id"], subido, None)
    assert salida["estado"] == "factor_pendiente" and salida["version"] == 2
    assert salida["factores_pendientes"][0]["linea"] == linea
    with pytest.raises(HTTPException):
        rr.validar_corregido(revision["id"], subido, None)
    final = rr.reanudar_revision(revision["id"], 2, {linea: "YPC"}, None)
    assert final["estado"] == "validado" and final["version"] == 3
    ws = openpyxl.load_workbook(archivo).active
    assert ws.cell(2, cols["PUBLICO"]).value == 987.65
    assert ws.cell(2, cols["MINIMO"]).value == pytest.approx(100 / .6 * .8)
    assert ws.cell(2, cols["Línea"]).value == linea
    with pytest.raises(HTTPException):
        rr.reanudar_revision(revision["id"], 2, {linea: "YPC"}, None)


def test_factor_manual_conserva_excel_hasta_completar_precios(entorno):
    archivo, revision = crear_reporte_linea_pendiente(entorno)
    wb = openpyxl.load_workbook(archivo)
    cols = {c.value: c.column for c in wb.active[1]}
    wb.active.cell(2, cols["Línea"], "ZZ9")
    salida = rr.validar_corregido(revision["id"], bytes_libro(wb), None)
    manual = rr.reanudar_revision(revision["id"], salida["version"], {"ZZ9": "LLENADO_MANUAL"}, None)
    assert manual["estado"] == "pendiente" and manual["factores_pendientes"] == []
    assert manual["version"] == 3
    wb = openpyxl.load_workbook(archivo)
    for p in d.PRECIOS:
        wb.active.cell(2, cols[p], 123.45)
    assert rr.validar_corregido(revision["id"], bytes_libro(wb), None)["estado"] == "validado"


@pytest.mark.parametrize("linea", ["DEMASIADO", "A B", "=A1", "", "Ñ"])
def test_rechaza_formato_linea_incompatible_con_sae(entorno, linea):
    archivo, revision = crear_reporte_linea_pendiente(entorno)
    wb = openpyxl.load_workbook(archivo)
    wb.active.cell(2, excel.COLUMNAS_ASPEL.index("Línea") + 1, linea)
    with pytest.raises(HTTPException) as exc:
        rr.validar_corregido(revision["id"], bytes_libro(wb), None)
    assert exc.value.status_code == 422


def test_api_excel_factor_pendiente_continua_y_guarda_contexto(entorno, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.v1.routes import almacen, chat
    from app.core.security import obtener_usuario_opcional
    from app.schemas.chat import ChatRequest
    archivo, revision = crear_reporte_linea_pendiente(entorno)
    wb = openpyxl.load_workbook(archivo)
    cols = {c.value: c.column for c in wb.active[1]}
    wb.active.cell(2, cols["Línea"], "ZZ9")
    wb.active.cell(2, cols["PUBLICO"], 987.65)
    app = FastAPI()
    app.include_router(almacen.router, prefix="/api/v1")
    app.dependency_overrides[obtener_usuario_opcional] = lambda: None
    client = TestClient(app)
    ruta = f"/api/v1/almacen/reportes/{revision['id']}"
    response = client.post(ruta + "/validar?session_id=chat-uno", files={"archivo": ("corregido.xlsx", bytes_libro(wb))})
    assert response.status_code == 200
    salida = response.json()
    assert salida["estado"] == "factor_pendiente"
    assert "línea ZZ9" in salida["resumen_revision"]
    assert client.get(ruta + "?session_id=chat-uno").json()["interaccion"]["id"] == salida["interaccion"]["id"]
    assert client.get(ruta + "/archivo?session_id=chat-uno&formato=tabs").status_code == 409
    monkeypatch.setattr(chat, "_ejecutar_chat_impl", lambda *a: pytest.fail("La confirmación no debe llamar al modelo"))
    i = salida["interaccion"]
    r = {"factor:ZZ9": {"opcion": "YPC", "recordar": False, "campos": {}}}
    req = ChatRequest(session_id="chat-uno", mensaje="Aplicar decisiones y continuar", decisiones=envio(i, r, "confirmar"))
    final = chat._ejecutar_chat(req)
    assert final.revision_reporte["estado"] == "validado"
    assert "ZZ9" in final.respuesta and "factor YPC" in final.respuesta and "PRUEBA-4000D" in final.respuesta
    assert client.get(ruta + "/archivo?session_id=chat-uno&formato=tabs").status_code == 200
    memoria = chat._obtener_mensajes_previos_bd("chat-uno", None)
    assert any("factor YPC" in str(m.content) for m in memoria)
    with pytest.raises(HTTPException):
        chat._ejecutar_chat(req)


def test_solo_lineas_pendientes_pueden_editarse_y_compra_se_conserva(entorno):
    archivo, revision = crear_reporte(entorno)
    wb = corregir(archivo)
    wb.active.cell(2, excel.COLUMNAS_ASPEL.index("Línea") + 1, "ZZ9")
    with pytest.raises(HTTPException):
        rr.validar_corregido(revision["id"], bytes_libro(wb), None)
    archivo, revision = crear_reporte_linea_pendiente(entorno)
    wb = openpyxl.load_workbook(archivo)
    wb.active.cell(2, excel.COLUMNAS_ASPEL.index("Línea") + 1, "YPC")
    wb.active.cell(2, excel.COLUMNAS_ASPEL.index("PRECIO COMPRA") + 1, 101)
    with pytest.raises(HTTPException):
        rr.validar_corregido(revision["id"], bytes_libro(wb), None)


def test_correccion_proveedor_actualiza_consolidado_sin_borrar_otros_pendientes(entorno):
    mini, rm = crear_reporte_linea_pendiente(entorno)
    # Conservar una proyección con un producto y crear un consolidado de dos.
    df = pd.read_excel(mini).reindex(columns=excel.COLUMNAS_ASPEL)
    df2 = df.copy()
    df2["Clave Artículo"] = "OTRO-4000D"
    combinado = pd.concat([df, df2], ignore_index=True)
    combinado.attrs["meta_por_clave"] = {k: {"manual": True, "linea_pendiente": True} for k in ("PRUEBA-4000D", "OTRO-4000D")}
    base = excel.guardar_en_base_acumulada(combinado, str(entorno[0]), limpiar_previos=True, prefijo="CONSOLIDADO")
    rb = rr.revision_actual(base, "chat-uno", None)
    wb = openpyxl.load_workbook(rr.directorio() / (rm["id"] + ".xlsx"))
    wb.active.cell(2, excel.COLUMNAS_ASPEL.index("Línea") + 1, "YPC")
    rr.validar_corregido(rm["id"], bytes_libro(wb), None)
    parcial = rr.cargar(rb["id"], uid=None)
    assert parcial["version"] == 2
    assert [p["producto"] for p in parcial["pendientes"]] == ["OTRO-4000D"]
    ws = openpyxl.load_workbook(base).active
    assert ws.cell(2, excel.COLUMNAS_ASPEL.index("Línea") + 1).value == "YPC"
    assert ws.cell(3, excel.COLUMNAS_ASPEL.index("Línea") + 1).value is None


def test_error_al_confirmar_factor_conserva_excel_y_ofrece_reintento_explicito(entorno, monkeypatch):
    from app.api.v1.routes import chat
    from app.schemas.chat import ChatRequest
    archivo, revision = crear_reporte_linea_pendiente(entorno)
    wb = openpyxl.load_workbook(archivo)
    wb.active.cell(2, excel.COLUMNAS_ASPEL.index("Línea") + 1, "ZZ9")
    salida = rr.validar_corregido(revision["id"], bytes_libro(wb), None)
    i = d.registrar("chat-uno", None, {"lineas_sin_factor": salida["factores_pendientes"]},
        "revisar_reporte_almacen", {"reporte_id": revision["id"], "version": salida["version"]})
    def fallar(*a, **kw):
        raise HTTPException(503, "Drive no pudo actualizarse. El TXT sigue bloqueado.")
    monkeypatch.setattr(rr, "reanudar_revision", fallar)
    r = {"factor:ZZ9": {"opcion": "YPC", "recordar": False, "campos": {}}}
    respuesta = chat._ejecutar_chat(ChatRequest(session_id="chat-uno", mensaje="Confirmar", decisiones=envio(i, r, "confirmar")))
    assert respuesta.avisos[0]["nivel"] == "error"
    assert respuesta.interaccion["estado"] == "pendiente" and respuesta.interaccion["id"] != i["id"]
    assert rr.cargar(revision["id"], uid=None)["version"] == salida["version"]
