from pathlib import Path

from app.core.config import settings
from app.services.almacen.apoyo import (
    _coinciden,
    _leer_desde_txt,
    buscar_dato,
    emparejar_conceptos_con_apoyo,
)
from app.services.almacen.excel import procesar_xml
from app.services.almacen.factores import resolver_linea
from app.services.almacen.fuentes import google_drive_client, organizador


def test_coinciden_codigos_con_espacios_y_guiones() -> None:
    assert _coinciden("FL69221", "FL 69221")
    apoyo = [
        {
            "clave_articulo": "FL69221",
            "codigo_norm": "FL69221",
            "linea": "PKRF",
            "descripcion_corta": "FILTRO LUBRICANTE",
            "numero_proveedor": "69",
        }
    ]
    dato = buscar_dato(apoyo, "FL 69221")
    assert dato is not None
    assert dato["clave_articulo"] == "FL69221"
    assert dato["linea"] == "PKRF"


def test_txt_btt_bandas_linea_vacia_y_emparejamiento_posicional(tmp_path: Path) -> None:
    contenido_txt = "\n".join(
        [
            "        Proveedor:      (            544)                                                         COMPRA      RCO13642",
            "          Cantidad  Cve.Art.          Cve.Sat/UM      Linea     Descripción                               % Desc.   Costo unitario          Importe",
            "                6.00BX78                              BAN     BANDA BX78                                      0.00        154.4600              926.76",
            "                6.00AX41                                      BANDA AX41                                      0.00          46.2400             277.44",
            "                6.00AX43                                      BANDA AX43                                      0.00          48.4900             290.94",
            "                6.008PK1855                                   BANDA 8PK1855                                   0.00        233.6600            1,401.96",
        ]
    )
    ruta_txt = tmp_path / "BTT.txt"
    ruta_txt.write_text(contenido_txt, encoding="utf-8")

    datos = _leer_desde_txt(str(ruta_txt))
    assert len(datos) == 4

    por_cod = {d["clave_articulo"]: d for d in datos}
    assert por_cod["AX41"]["descripcion_corta"] == "BANDA AX41"
    assert por_cod["AX43"]["descripcion_corta"] == "BANDA AX43"
    assert por_cod["8PK1855"]["descripcion_corta"] == "BANDA 8PK1855"
    # Todas las filas heredan la linea unica "BAN" del documento
    assert all(d["linea"] == "BAN" for d in datos)

    info_ban = resolver_linea("BAN")
    assert info_ban["linea_resuelta"] == "BANDA"

    conceptos = [
        {"no_identificacion": "BX78", "descripcion": "BX78 BANDA DENTADA"},
        {"no_identificacion": "AX41", "descripcion": "AX41 BANDA DENTADA"},
        {"no_identificacion": "AX43", "descripcion": "AX43 BANDA DENTADA"},
        {"no_identificacion": "AMVPK81855", "descripcion": "8K730 BANDA RED POWER"},
    ]
    emparejados = emparejar_conceptos_con_apoyo(conceptos, datos)
    assert [d["clave_articulo"] for d in emparejados if d] == ["BX78", "AX41", "AX43", "8PK1855"]
    assert emparejados[3]["descripcion_corta"] == "BANDA 8PK1855"
    assert emparejados[3]["linea"] == "BAN"


def test_reubicar_carpetas_desanida_carpeta_fecha_dentro_de_otra_fecha(monkeypatch) -> None:
    monkeypatch.setattr(settings, "google_drive_folder_id", "docs-root")
    monkeypatch.setattr(organizador, "crear_cliente_drive", lambda: object())

    hijos = {
        "docs-root": [
            {"id": "entrada-id", "name": "ENTRADAS AL INVENTARIO", "mimeType": google_drive_client.MIME_CARPETA},
            {"id": "doc-id", "name": "DOCUMENTOS ENTRADA", "mimeType": google_drive_client.MIME_CARPETA},
        ],
        "doc-id": [],
        "entrada-id": [
            {"id": "f-20", "name": "20-10-2026", "mimeType": google_drive_client.MIME_CARPETA},
        ],
        "f-20": [
            {"id": "f-30-nested", "name": "30-10-2026", "mimeType": google_drive_client.MIME_CARPETA},
        ],
        "f-30-nested": [
            {"id": "xml-1", "name": "factura.xml", "mimeType": "text/xml"},
        ],
    }

    def mock_buscar_hija(cliente, nombre: str, padre: str) -> str | None:
        for item in hijos.get(padre, []):
            if item.get("mimeType") == google_drive_client.MIME_CARPETA and item.get("name") == nombre:
                return item["id"]
        return None

    movimientos: list[tuple[str, str, str | None]] = []

    monkeypatch.setattr(organizador, "_listar_hijos", lambda cliente, cid: list(hijos.get(cid, [])))
    monkeypatch.setattr(organizador, "buscar_carpeta_hija", mock_buscar_hija)
    monkeypatch.setattr(
        organizador,
        "mover_archivo",
        lambda cliente, fid, dest, carpeta_origen_id=None: movimientos.append((fid, dest, carpeta_origen_id)),
    )

    res = organizador.reubicar_carpetas_mal_ubicadas(cliente=object())
    assert ("f-30-nested", "entrada-id", "f-20") in movimientos
    assert "30-10-2026" in res["carpetas_reubicadas"]


def test_lote_real_30_10_2026_si_existe() -> None:
    carpeta_30 = Path(r"C:\Users\rober\Proyectos\30-10-2026")
    if not carpeta_30.exists():
        return

    xml_aze = next(carpeta_30.rglob("AZE841112TH6_MAY73109.xml"), None)
    assert xml_aze is not None
    df_aze = procesar_xml(str(xml_aze), str(xml_aze.parent))
    fila_fl = df_aze[df_aze["Clave Artículo"] == "FL69221"]
    assert len(fila_fl) == 1
    assert fila_fl.iloc[0]["Línea"] == "PKRF"
    assert float(fila_fl.iloc[0]["MOSTRADOR"]) > 0

    xml_btt = next(carpeta_30.rglob("BTT150921F46_Factura_RCO13642_20261027.xml"), None)
    assert xml_btt is not None
    df_btt = procesar_xml(str(xml_btt), str(xml_btt.parent))
    assert len(df_btt) == 10
    assert list(df_btt["Línea"].unique()) == ["BANDA"]
    assert "8PK1855" in set(df_btt["Clave Artículo"])
    assert "BANDA AX41" in set(df_btt["DESCRIPCION"])
    assert "BANDA AX43" in set(df_btt["DESCRIPCION"])
    assert list(df_btt["PROVEEDOR"].unique()) == ["544"]
