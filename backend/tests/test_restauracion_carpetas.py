import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from langchain_core.runnables.config import var_child_runnable_config

from app.services.almacen.fuentes import limpieza, operaciones_drive as diario
from app.services.almacen.fuentes import google_drive_client as drive
from app.agents.tools.drive_tools import gestionar_archivos_drive

MIME = drive.MIME_CARPETA
REFERENCIA = Path(r"C:\Users\rober\Proyectos\Docs\DOCUMENTOS ENTRADA\2026\NOVIEMBRE\17-11-2026")


class DriveFalso:
    def __init__(self):
        self.items = {}
        self.escrituras = []
        self.denegar = None
        self.perder_respuesta = None

    def agregar(self, id, nombre, padre=None, carpeta=False):
        self.items[id] = {"id": id, "name": nombre, "parents": [padre] if padre else [],
                          "mimeType": MIME if carpeta else "application/octet-stream", "trashed": False}

    def files(self):
        return self

    def get(self, fileId, **kwargs):
        return SimpleNamespace(execute=lambda **kw: dict(self.items[fileId]))

    def list(self, q, **kwargs):
        padre = re.search(r"'([^']+)' in parents", q).group(1)
        return SimpleNamespace(execute=lambda **kw: {"files": [dict(i) for i in self.items.values() if padre in i["parents"] and not i["trashed"]]})

    def update(self, fileId, body=None, addParents=None, **kwargs):
        def ejecutar(num_retries=0):
            assert num_retries == 0
            self.escrituras.append((fileId, "papelera" if body else "mover"))
            if self.denegar == fileId:
                error = RuntimeError("sin permiso")
                error.resp = SimpleNamespace(status=403)
                raise error
            if body:
                self.items[fileId].update(body)
            else:
                self.items[fileId]["parents"] = [addParents]
            if self.perder_respuesta == fileId:
                raise ConnectionError("respuesta perdida tras escribir")
            return dict(self.items[fileId])
        return SimpleNamespace(execute=ejecutar)


@pytest.fixture
def entorno(monkeypatch, tmp_path):
    motor = create_engine(f"sqlite:///{tmp_path / 'diario.db'}")
    monkeypatch.setattr(diario, "engine", motor)
    monkeypatch.setattr(limpieza, "CARPETA_DATOS", tmp_path)
    monkeypatch.setattr(limpieza.settings, "google_drive_folder_id", "root")
    cliente = DriveFalso()
    for id, nombre, padre in [("root", "docs", None), ("docs", "DOCUMENTOS ENTRADA", "root"), ("year", "2026", "docs"), ("mes", "NOVIEMBRE", "year")]:
        cliente.agregar(id, nombre, padre, True)
    monkeypatch.setattr(limpieza, "crear_cliente_drive", lambda: cliente)
    monkeypatch.setattr(drive, "crear_cliente_drive", lambda: cliente)
    yield cliente, tmp_path
    motor.dispose()


def fecha(cliente, dia="17", completo=False):
    id = "fecha-" + dia
    nombre = f"{dia}-11-2026"
    cliente.agregar(id, nombre, "mes", True)
    for proveedor in ("A", "B"):
        carpeta = id + proveedor
        cliente.agregar(carpeta, proveedor, id, True)
        cliente.agregar(carpeta + "xml", proveedor + ".xml", carpeta)
        cliente.agregar(carpeta + "txt", proveedor + ".txt", carpeta)
        cliente.agregar(carpeta + "pdf", proveedor + ".pdf", carpeta)
        for sufijo in (".xlsx", "_COMAS.txt", "_TABS.txt"):
            cliente.agregar(carpeta + sufijo, f"ENTRADAS_ALMACEN_{proveedor}_{nombre}{sufijo}", carpeta)
    if completo:
        for sufijo in (".xlsx", "_COMAS.txt", "_TABS.txt"):
            cliente.agregar(id + sufijo, f"ENTRADAS_ALMACEN_{nombre}{sufijo}", id)
    return id


def restaurar(rutas):
    return json.loads(gestionar_archivos_drive.invoke(
        {"accion": "restablecer_carpeta", "rutas_origen": rutas},
        config={"configurable": {"drive_request_id": "restauracion"}},
    ))


def test_restaura_estado_parcial_del_17_y_es_idempotente(entorno):
    cliente, tmp = entorno
    id = fecha(cliente)
    estado = {"archivos": {id + "Axml": "v1", "otra-fecha": "v2"}}
    (tmp / limpieza.NOMBRE_ESTADO).write_text(json.dumps(estado))
    (tmp / "FACTORES_PERSONALIZADOS.json").write_text("{}")
    resultado = restaurar(["17-11-2026"])
    assert resultado["ok"]
    originales = [i for i in cliente.items.values() if i["id"].startswith(id) and not i["trashed"] and i["id"] != id]
    assert len(originales) == 6
    assert all(i["parents"] == [id] for i in originales)
    assert cliente.items[id]["parents"] == ["mes"]
    assert not cliente.items[id]["trashed"]
    assert sum(i["trashed"] for i in cliente.items.values()) == 8
    assert json.loads((tmp / limpieza.NOMBRE_ESTADO).read_text())["archivos"] == {"otra-fecha": "v2"}
    assert (tmp / "FACTORES_PERSONALIZADOS.json").exists()
    escrituras = list(cliente.escrituras)
    assert restaurar(["id:" + id])["ok"]
    assert cliente.escrituras == escrituras


def test_varias_fechas_y_reportes_generales(entorno):
    cliente, _ = entorno
    uno = fecha(cliente, "17", True)
    dos = fecha(cliente, "18", True)
    tercero = fecha(cliente, "19", True)
    assert restaurar(["17-11-2026", "18-11-2026"])["ok"]
    assert all(i["trashed"] for i in cliente.items.values() if i["name"].startswith("ENTRADAS_ALMACEN_") and i["id"].startswith((uno, dos)))
    assert not any(i["trashed"] for i in cliente.items.values() if i["id"].startswith(tercero))


def test_error_moviendo_no_elimina_originales_ni_carpetas(entorno):
    cliente, _ = entorno
    id = fecha(cliente)
    cliente.denegar = id + "Axml"
    resultado = restaurar(["17-11-2026"])
    assert resultado["estado"] == "parcial"
    assert not any(i["trashed"] for i in cliente.items.values())
    cliente.denegar = None
    assert restaurar(["17-11-2026"])["ok"]


def test_error_en_papelera_conserva_carpeta_y_retoma(entorno):
    cliente, _ = entorno
    id = fecha(cliente)
    cliente.denegar = id + "A.xlsx"
    assert not restaurar(["17-11-2026"])["ok"]
    assert all(not cliente.items[id + p + ext]["trashed"] for p in ("A", "B") for ext in ("xml", "pdf", "txt"))
    assert not cliente.items[id + "A"]["trashed"]
    cliente.denegar = None
    assert restaurar(["17-11-2026"])["ok"]


def test_respuesta_perdida_al_enviar_papelera_se_verifica(entorno):
    cliente, _ = entorno
    id = fecha(cliente)
    cliente.perder_respuesta = id + "A.xlsx"
    assert restaurar(["17-11-2026"])["ok"]
    assert cliente.escrituras.count((id + "A.xlsx", "papelera")) == 1


def test_prevalida_todas_las_fechas_antes_de_escribir(entorno):
    cliente, _ = entorno
    fecha(cliente)
    resultado = restaurar(["17-11-2026", "fecha-inexistente"])
    assert not resultado["ok"]
    assert cliente.escrituras == []


def test_homonimos_pide_elegir_y_no_modifica(entorno):
    cliente, _ = entorno
    fecha(cliente)
    cliente.agregar("duplicada", "17-11-2026", "mes", True)
    resultado = restaurar(["17-11-2026"])
    assert resultado["requiere_confirmacion"]
    assert cliente.escrituras == []


def test_desconocidos_y_txt_de_apoyo_no_se_borran(entorno):
    cliente, _ = entorno
    id = fecha(cliente)
    cliente.agregar("ajeno", "precios.xlsx", id + "A")
    assert not restaurar(["17-11-2026"])["ok"]
    assert cliente.escrituras == []


def test_restauracion_global_no_crea_bandeja_antigua(entorno):
    cliente, _ = entorno
    fecha(cliente)
    fecha(cliente, "18")
    assert limpieza.restaurar_entorno_pruebas()["ok"]
    assert all(i["name"] != "ENTRADAS AL INVENTARIO" for i in cliente.items.values())


def test_chat_recupera_restauracion_real_si_falla_la_redaccion(entorno, monkeypatch):
    from app.api.v1.routes import chat
    from app.schemas.chat import ChatRequest
    cliente, _ = entorno
    fecha(cliente)
    invocaciones = []
    guardadas = []
    class Grafo:
        def invoke(self, estado, config):
            invocaciones.append(config)
            gestionar_archivos_drive.invoke({"accion": "restablecer_carpeta", "ruta_origen": "17-11-2026"}, config=config)
            raise ConnectionError("error despues de restaurar")
    monkeypatch.setattr(chat, "grafo", Grafo())
    monkeypatch.setattr(chat, "_obtener_mensajes_previos_bd", lambda *a: [])
    monkeypatch.setattr(chat, "_guardar_interaccion_en_bd", lambda **kw: guardadas.append(kw["respuesta_chat"]))
    respuesta = chat._ejecutar_chat(ChatRequest(mensaje="Restablece 17-11-2026", session_id="restauracion-real"))
    assert "Carpeta restablecida" in respuesta.respuesta
    assert "DOCUMENTOS ENTRADA/2026/NOVIEMBRE/17-11-2026" in respuesta.respuesta
    assert len(invocaciones) == 1
    assert guardadas[0].respuesta == respuesta.respuesta
    assert len(cliente.escrituras) == len(set(cliente.escrituras))


def test_ordenar_y_auditar_no_sacan_pendientes_a_bandeja_antigua(entorno):
    from app.services.almacen.fuentes import organizador, navegador_drive
    cliente, _ = entorno
    cliente.agregar("fecha", "17-11-2026", "mes", True)
    cliente.agregar("xml", "factura.xml", "fecha")
    assert organizador.ordenar_todo_drive(cliente, "root")["ok"]
    auditoria = navegador_drive.auditar_facturas_drive(cliente=cliente, carpeta_raiz_id="root")
    assert auditoria["resumen_hallazgos"]["carpetas_mal_ubicadas"] == []
    assert cliente.escrituras == []
    assert cliente.items["fecha"]["parents"] == ["mes"]


def test_restauracion_emite_pasos_reales_y_resultado_verificado(entorno):
    from app.api.v1.routes.chat import ActividadHandler
    cliente, _ = entorno
    fecha(cliente)
    handler = ActividadHandler()
    gestionar_archivos_drive.invoke({"accion": "restablecer_carpeta", "ruta_origen": "17-11-2026"}, config={"callbacks": [handler]})
    pasos = [a for a in handler.actividades if a["tipo"] == "accion"]
    assert [p["texto"] for p in pasos] == ["Buscando la carpeta", "Restaurando la carpeta", "Verificando su ubicación"]
    assert len({p["id"] for p in pasos}) == 3
    assert all(p["estado"] == "completado" for p in pasos)
    assert handler.actividades[0]["estado"] == "completado"


def test_error_restaurando_no_marca_verificacion_como_completada(entorno):
    from app.api.v1.routes.chat import ActividadHandler
    cliente, _ = entorno
    id = fecha(cliente)
    cliente.denegar = id + "Axml"
    handler = ActividadHandler()
    gestionar_archivos_drive.invoke({"accion": "restablecer_carpeta", "ruta_origen": "17-11-2026"}, config={"callbacks": [handler]})
    assert handler.actividades[0]["estado"] == "parcial"
    assert any(a["texto"] == "Restaurando la carpeta" and a["estado"] == "parcial" for a in handler.actividades)
    assert not any(a["texto"] == "Verificando su ubicación" and a["estado"] == "completado" for a in handler.actividades)


@pytest.mark.skipif(not REFERENCIA.is_dir(), reason="Copia de Drive local no disponible")
def test_copia_real_del_17_solo_lectura_con_drive_simulado(entorno):
    cliente, _ = entorno
    cliente.agregar("fecha-real", REFERENCIA.name, "mes", True)
    ids = {REFERENCIA: "fecha-real"}
    for indice, archivo in enumerate(sorted(REFERENCIA.rglob("*"), key=lambda p: len(p.parts))):
        id = "local-" + str(indice)
        ids[archivo] = id
        cliente.agregar(id, archivo.name, ids[archivo.parent], archivo.is_dir())
    xmls = {i["id"] for i in cliente.items.values() if i["name"].lower().endswith(".xml")}
    reportes = {i["id"] for i in cliente.items.values() if limpieza.es_reporte_generado(i["name"])}
    assert len(xmls) == 2 and len(reportes) == 6
    assert restaurar(["17-11-2026"])["ok"]
    assert all(cliente.items[id]["parents"] == ["fecha-real"] and not cliente.items[id]["trashed"] for id in xmls)
    assert all(cliente.items[id]["trashed"] for id in reportes)
