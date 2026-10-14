from pathlib import Path

import pandas as pd

from app.core.config import settings
from app.services.almacen.fuentes import google_drive_client, sincronizador, subidor
from app.services.almacen.fuentes.google_drive import CarpetaFactura, DriveArchivo
from app.services.almacen.extractor import leer_meta


def test_subida_web_usa_entrada_y_fecha_bajo_docs(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(settings, "google_drive_folder_id", "docs-root")
    monkeypatch.setattr(subidor, "crear_cliente_drive", lambda: object())
    monkeypatch.setattr(subidor, "_nombre_carpeta_carga", lambda: "18-03-2026")

    carpetas: dict[tuple[str, str], str] = {}
    llamadas_carpetas: list[tuple[str, str]] = []

    def buscar_o_crear(cliente, nombre: str, padre: str) -> str:
        llamadas_carpetas.append((nombre, padre))
        carpetas[(nombre, padre)] = f"id-{len(carpetas) + 1}"
        return carpetas[(nombre, padre)]

    subidas: list[tuple[str, str]] = []
    monkeypatch.setattr(subidor, "buscar_o_crear_carpeta", buscar_o_crear)
    monkeypatch.setattr(subidor, "listar_archivos_carpeta", lambda cliente, carpeta_id: [])
    monkeypatch.setattr(
        subidor,
        "subir_archivo",
        lambda cliente, ruta, carpeta_id: subidas.append((ruta.name, carpeta_id)),
    )

    xml = tmp_path / "factura-100.xml"
    pdf = tmp_path / "factura-100.pdf"
    resultado = subidor.subir_documentos_drive([xml, pdf])

    assert llamadas_carpetas == [
        ("ENTRADAS AL INVENTARIO", "docs-root"),
        ("18-03-2026", "id-1"),
    ]
    assert {carpeta_id for _, carpeta_id in subidas} == {"id-2"}
    assert resultado["subidos"] == 2


def test_busqueda_historica_se_limita_a_documentos_entrada_y_fecha(monkeypatch) -> None:
    carpetas = {
        "docs-root": [
            {"id": "archive", "name": "DOCUMENTOS ENTRADA", "mimeType": google_drive_client.MIME_CARPETA},
            {"id": "old-date", "name": "18-03-2025", "mimeType": google_drive_client.MIME_CARPETA},
        ],
        "archive": [
            {"id": "date", "name": "18-03-2026", "mimeType": google_drive_client.MIME_CARPETA},
        ],
        "date": [
            {"id": "supplier", "name": "Proveedor SA - 18-03-2026", "mimeType": google_drive_client.MIME_CARPETA},
            {"id": "batch", "name": "ENTRADAS_ALMACEN_18-03-2026.xlsx", "mimeType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
            {"id": "invoice", "name": "factura.xml", "mimeType": "text/xml"},
        ],
        "supplier": [
            {"id": "individual", "name": "ENTRADAS_ALMACEN_Proveedor_18-03-2026_factura.xlsx", "mimeType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
        ],
        "old-date": [
            {"id": "old-report", "name": "ENTRADAS_ALMACEN_18-03-2025.xlsx", "mimeType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
        ],
    }
    monkeypatch.setattr(settings, "google_drive_folder_id", "docs-root")
    monkeypatch.setattr(google_drive_client, "_listar_hijos", lambda cliente, carpeta_id: carpetas[carpeta_id])

    reportes = google_drive_client.buscar_reportes_historicos("2026-03-18", cliente=object())

    assert [reporte["id"] for reporte in reportes] == ["batch", "individual"]
    assert all(reporte["fecha"] == "18-03-2026" for reporte in reportes)


def test_leer_meta_extrae_nombre_del_proveedor_desde_el_xml(tmp_path: Path) -> None:
    ruta_xml = tmp_path / "factura.xml"
    ruta_xml.write_text(
        '<cfdi:Comprobante xmlns:cfdi="http://www.sat.gob.mx/cfd/4" '
        'Folio="100" Fecha="2026-03-18T12:00:00">'
        '<cfdi:Emisor Nombre="Proveedor Ejemplo, S.A." Rfc="AAA010101AAA" />'
        "</cfdi:Comprobante>",
        encoding="utf-8",
    )

    meta = leer_meta(ruta_xml)

    assert meta["proveedor_nombre"] == "Proveedor Ejemplo, S.A."


def test_sincronizacion_archiva_por_nombre_proveedor_y_fecha_de_carga(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(settings, "google_drive_folder_id", "docs-root")
    monkeypatch.setattr(sincronizador, "CARPETA_DATOS", tmp_path)
    monkeypatch.setattr(sincronizador, "crear_cliente_drive", lambda: object())
    monkeypatch.setattr(sincronizador, "buscar_carpeta_hija", lambda *args: "input-root")

    carpeta = CarpetaFactura(
        id="load-folder",
        nombre="18-03-2026",
        archivos=(
            DriveArchivo("xml-id", "factura-100.xml", "text/xml", "v1", "load-folder"),
            DriveArchivo("pdf-id", "factura-100.pdf", "application/pdf", "v1", "load-folder"),
        ),
    )

    def listar(cliente, carpeta_raiz_id):
        assert carpeta_raiz_id == "input-root"
        return [carpeta]

    monkeypatch.setattr(sincronizador, "listar_carpetas_factura", listar)

    carpetas_creadas: dict[tuple[str, str], str] = {}

    def buscar_o_crear(cliente, nombre: str, padre: str) -> str:
        key = (nombre, padre)
        if key not in carpetas_creadas:
            carpetas_creadas[key] = f"drive-{len(carpetas_creadas) + 1}"
        return carpetas_creadas[key]

    monkeypatch.setattr(sincronizador, "buscar_o_crear_carpeta", buscar_o_crear)
    monkeypatch.setattr(sincronizador, "descargar_archivo", lambda cliente, archivo, destino: destino.write_text("doc"))
    monkeypatch.setattr(
        "app.services.almacen.extractor.leer_meta",
        lambda ruta: {"folio": 100, "year": "2026", "rfc": "AAA010101AAA", "proveedor_nombre": "Proveedor Ejemplo, S.A."},
    )
    monkeypatch.setattr(
        "app.services.almacen.apoyo._folio_coincide_con_archivo",
        lambda *args, **kwargs: True,
    )
    monkeypatch.setattr(
        sincronizador,
        "procesar_xml",
        lambda ruta, carpeta: pd.DataFrame([{"producto": "válvula"}]),
    )

    def guardar_excel(df, carpeta_local, limpiar_previos=True, prefijo="reporte", guardar_resumen=True):
        ruta = Path(carpeta_local) / f"{prefijo}.xlsx"
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_bytes(b"excel")
        return str(ruta)

    monkeypatch.setattr(sincronizador, "guardar_en_base_acumulada", guardar_excel)

    movimientos: list[tuple[str, str]] = []
    subidas: list[tuple[str, str]] = []
    monkeypatch.setattr(
        google_drive_client,
        "mover_archivo",
        lambda cliente, archivo_id, carpeta_id: movimientos.append((archivo_id, carpeta_id)),
    )
    monkeypatch.setattr(
        google_drive_client,
        "subir_archivo",
        lambda cliente, ruta, carpeta_id: subidas.append((Path(ruta).name, carpeta_id)),
    )

    resultado = sincronizador.sincronizar_drive()

    archive_id = carpetas_creadas[("DOCUMENTOS ENTRADA", "docs-root")]
    date_id = carpetas_creadas[("18-03-2026", archive_id)]
    supplier_id = carpetas_creadas[("Proveedor Ejemplo, S.A. - 18-03-2026", date_id)]
    assert set(movimientos) == {("xml-id", supplier_id), ("pdf-id", supplier_id)}
    assert (
        "ENTRADAS_ALMACEN_Proveedor Ejemplo, S.A._18-03-2026.xlsx",
        supplier_id,
    ) in subidas
    assert ("ENTRADAS_ALMACEN_18-03-2026.xlsx", date_id) in subidas
    assert resultado["productos"] == 1


def test_deteccion_y_reubicacion_de_carpetas_sin_reporte_en_documentos_entrada(monkeypatch) -> None:
    from app.services.almacen.fuentes import organizador

    estructura = {
        "docs-root": [
            {"id": "hist-id", "name": "DOCUMENTOS ENTRADA", "mimeType": google_drive_client.MIME_CARPETA},
            {"id": "in-id", "name": "ENTRADAS AL INVENTARIO", "mimeType": google_drive_client.MIME_CARPETA},
        ],
        "hist-id": [
            {"id": "bad-folder", "name": "20-03-2026", "mimeType": google_drive_client.MIME_CARPETA},
            {"id": "good-folder", "name": "18-03-2026", "mimeType": google_drive_client.MIME_CARPETA},
        ],
        "bad-folder": [
            {"id": "xml-200", "name": "factura-200.xml", "mimeType": "text/xml"},
            {"id": "txt-200", "name": "factura-200.txt", "mimeType": "text/plain"},
        ],
        "good-folder": [
            {"id": "rep-18", "name": "ENTRADAS_ALMACEN_18-03-2026.xlsx", "mimeType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
        ],
        "in-id": [],
    }

    movimientos: list[tuple[str, str]] = []
    monkeypatch.setattr(settings, "google_drive_folder_id", "docs-root")
    monkeypatch.setattr(organizador, "_listar_hijos", lambda cliente, carpeta_id: estructura.get(carpeta_id, []))
    monkeypatch.setattr(
        organizador,
        "buscar_carpeta_hija",
        lambda cliente, nombre, padre: next(
            (i["id"] for i in estructura.get(padre, []) if i.get("mimeType") == google_drive_client.MIME_CARPETA and i.get("name") == nombre),
            None,
        ),
    )
    monkeypatch.setattr(organizador, "buscar_o_crear_carpeta", lambda cliente, nombre, padre: "in-id")
    monkeypatch.setattr(
        organizador,
        "mover_archivo",
        lambda cliente, archivo_id, destino_id: movimientos.append((archivo_id, destino_id)),
    )

    res = organizador.reubicar_carpetas_mal_ubicadas(cliente=object(), carpeta_raiz_id="docs-root")

    assert res["carpetas_reubicadas"] == ["20-03-2026"]
    assert ("bad-folder", "in-id") in movimientos
    advertencia = organizador.construir_advertencia_ubicacion(res["carpetas_reubicadas"])
    assert "20-03-2026" in advertencia
    assert "DOCUMENTOS ENTRADA" in advertencia
    assert "ENTRADAS AL INVENTARIO" in advertencia


def test_comandos_conversacionales_revisar_mover_y_ordenar(monkeypatch) -> None:
    from app.services.almacen.fuentes import organizador

    estructura = {
        "docs-root": [
            {"id": "hist-id", "name": "DOCUMENTOS ENTRADA", "mimeType": google_drive_client.MIME_CARPETA},
            {"id": "in-id", "name": "ENTRADAS AL INVENTARIO", "mimeType": google_drive_client.MIME_CARPETA},
        ],
        "in-id": [
            {"id": "pending-in", "name": "21-03-2026", "mimeType": google_drive_client.MIME_CARPETA},
            {"id": "done-in", "name": "19-03-2026", "mimeType": google_drive_client.MIME_CARPETA},
            {"id": "empty-in", "name": "Carpeta Vacia", "mimeType": google_drive_client.MIME_CARPETA},
            {"id": "loose-xml", "name": "suelto_22-03-2026.xml", "mimeType": "text/xml"},
        ],
        "pending-in": [
            {"id": "xml-21", "name": "fac21.xml", "mimeType": "text/xml"},
        ],
        "done-in": [
            {"id": "xml-19", "name": "fac19.xml", "mimeType": "text/xml"},
            {"id": "rep-19", "name": "ENTRADAS_ALMACEN_19-03-2026.xlsx", "mimeType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
        ],
        "empty-in": [],
        "hist-id": [
            {"id": "misplaced-hist", "name": "20-03-2026", "mimeType": google_drive_client.MIME_CARPETA},
        ],
        "misplaced-hist": [
            {"id": "xml-20", "name": "fac20.xml", "mimeType": "text/xml"},
        ],
    }

    monkeypatch.setattr(settings, "google_drive_folder_id", "docs-root")
    monkeypatch.setattr(organizador, "_listar_hijos", lambda cliente, carpeta_id: estructura.get(carpeta_id, []))
    monkeypatch.setattr(
        organizador,
        "buscar_carpeta_hija",
        lambda cliente, nombre, padre: next(
            (i["id"] for i in estructura.get(padre, []) if i.get("mimeType") == google_drive_client.MIME_CARPETA and i.get("name") == nombre),
            None,
        ),
    )
    monkeypatch.setattr(
        organizador,
        "buscar_o_crear_carpeta",
        lambda cliente, nombre, padre: next(
            (i["id"] for i in estructura.get(padre, []) if i.get("mimeType") == google_drive_client.MIME_CARPETA and i.get("name") == nombre),
            f"created-{nombre}-{padre}",
        ),
    )

    movimientos: list[tuple[str, str]] = []
    eliminados: list[str] = []
    monkeypatch.setattr(
        organizador,
        "mover_archivo",
        lambda cliente, archivo_id, destino_id: movimientos.append((archivo_id, destino_id)),
    )
    monkeypatch.setattr(
        organizador,
        "eliminar_archivo",
        lambda cliente, archivo_id: eliminados.append(archivo_id),
    )

    revision = organizador.revisar_carpetas_sin_reportes_drive(cliente=object(), carpeta_raiz_id="docs-root")
    assert revision["en_entradas_al_inventario"] == ["21-03-2026"]
    assert revision["en_documentos_entrada"] == ["20-03-2026"]
    assert revision["total_pendientes"] == 2

    orden = organizador.ordenar_todo_drive(
        cliente=object(),
        carpeta_raiz_id="docs-root",
        fecha_actual="13-10-2026",
    )
    assert orden["carpetas_reubicadas"] == ["20-03-2026"]
    assert orden["carpetas_con_reporte_movidas"] == ["19-03-2026"]
    assert orden["archivos_sueltos_acomodados"] == ["suelto_22-03-2026.xml"]
    assert orden["carpeta_archivos_sueltos"] == "ARCHIVOS_SUELTOS_13-10-2026"
    assert (
        "Por favor revisa la carpeta **ARCHIVOS_SUELTOS_13-10-2026** y organiza manualmente los archivos."
        in orden["advertencia_archivos_sueltos"]
    )
    assert orden["carpetas_vacias_eliminadas"] == ["Carpeta Vacia"]
    assert ("done-in", "hist-id") in movimientos
    assert ("loose-xml", "created-ARCHIVOS_SUELTOS_13-10-2026-docs-root") in movimientos
    assert ("empty-in" in eliminados)


def test_restaurar_entorno_pruebas_reutiliza_carpeta_fecha_sin_borrar(monkeypatch, tmp_path: Path) -> None:
    from app.services.almacen.fuentes import limpieza

    estructura = {
        "docs-root": [
            {"id": "hist-id", "name": "DOCUMENTOS ENTRADA", "mimeType": google_drive_client.MIME_CARPETA},
            {"id": "in-id", "name": "ENTRADAS AL INVENTARIO", "mimeType": google_drive_client.MIME_CARPETA},
        ],
        "in-id": [],
        "hist-id": [
            {"id": "date-28", "name": "28-09-2026", "mimeType": google_drive_client.MIME_CARPETA},
        ],
        "date-28": [
            {"id": "batch-rep", "name": "ENTRADAS_ALMACEN_28-09-2026.xlsx", "mimeType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
            {"id": "prov-folder", "name": "PROVEEDOR - 28-09-2026", "mimeType": google_drive_client.MIME_CARPETA},
        ],
        "prov-folder": [
            {"id": "prov-rep", "name": "ENTRADAS_ALMACEN_PROVEEDOR_28-09-2026.xlsx", "mimeType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
            {"id": "xml-1", "name": "factura.xml", "mimeType": "text/xml"},
            {"id": "txt-1", "name": "factura.txt", "mimeType": "text/plain"},
        ],
    }

    movimientos: list[tuple[str, str]] = []
    eliminados: list[str] = []

    monkeypatch.setattr(settings, "google_drive_folder_id", "docs-root")
    monkeypatch.setattr(limpieza, "CARPETA_DATOS", str(tmp_path))
    monkeypatch.setattr(limpieza, "crear_cliente_drive", lambda: object())
    monkeypatch.setattr(limpieza, "_listar_hijos", lambda cliente, carpeta_id: estructura.get(carpeta_id, []))
    monkeypatch.setattr(
        limpieza,
        "buscar_carpeta_hija",
        lambda cliente, nombre, padre: next(
            (i["id"] for i in estructura.get(padre, []) if i.get("mimeType") == google_drive_client.MIME_CARPETA and i.get("name") == nombre),
            None,
        ),
    )
    monkeypatch.setattr(limpieza, "buscar_o_crear_carpeta", lambda cliente, nombre, padre: "in-id")
    monkeypatch.setattr(
        limpieza,
        "mover_archivo",
        lambda cliente, archivo_id, destino_id: movimientos.append((archivo_id, destino_id)),
    )
    monkeypatch.setattr(
        limpieza,
        "eliminar_archivo",
        lambda cliente, archivo_id: eliminados.append(archivo_id),
    )

    res = limpieza.restaurar_entorno_pruebas()

    assert res["ok"] is True
    assert res["movidos"] == 2
    assert res["eliminados"] == 2
    assert res["advertencias"] == []
    assert ("xml-1", "date-28") in movimientos
    assert ("txt-1", "date-28") in movimientos
    assert ("date-28", "in-id") in movimientos
    assert "date-28" not in eliminados
    assert set(eliminados) == {"batch-rep", "prov-rep", "prov-folder"}


