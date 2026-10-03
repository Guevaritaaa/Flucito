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

    def guardar_excel(df, carpeta_local, limpiar_previos=True, prefijo="reporte"):
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
        "ENTRADAS_ALMACEN_Proveedor Ejemplo, S.A._18-03-2026_factura-100.xlsx",
        supplier_id,
    ) in subidas
    assert ("ENTRADAS_ALMACEN_18-03-2026.xlsx", date_id) in subidas
    assert resultado["productos"] == 1
