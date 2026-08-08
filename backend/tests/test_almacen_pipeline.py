from pathlib import Path

import pandas as pd

from app.services.almacen import apoyo, excel


def test_apoyo_txt_usa_folio_y_extension_mayuscula(tmp_path: Path) -> None:
    ruta = tmp_path / "FAC20261827.TXT"
    ruta.write_text("1.00ABC123 ADC Descripcion producto\n", encoding="utf-8")

    resultado = apoyo.obtener_apoyo_por_folio(str(tmp_path), "2026", 1827)

    assert resultado[0]["clave_articulo"] == "ABC123"
    assert resultado[0]["linea"] == "ADC"


def test_apoyo_empareja_codigo_por_prefijo() -> None:
    resultado = apoyo.buscar_dato(
        [{"codigo_norm": "ABC123X", "clave_articulo": "ABC123X"}],
        "ABC123",
    )

    assert resultado["clave_articulo"] == "ABC123X"


def test_procesar_carpeta_detecta_xml_en_mayusculas(
    tmp_path: Path,
    monkeypatch,
) -> None:
    ruta_xml = tmp_path / "FACTURA.XML"
    ruta_xml.write_text("contenido", encoding="utf-8")
    llamadas: list[Path] = []

    monkeypatch.setattr(
        excel,
        "procesar_xml",
        lambda ruta, carpeta: llamadas.append(Path(ruta)) or pd.DataFrame({"x": [1]}),
    )
    monkeypatch.setattr(excel, "guardar_en_base_acumulada", lambda df, carpeta: "ok")

    excel.procesar_carpeta(str(tmp_path))

    assert llamadas == [ruta_xml]


def test_formatea_fecha_y_deduplica_base(tmp_path: Path) -> None:
    assert excel._formatea_fecha("2026-08-04T00:00:00") == "04-08-2026"

    fila = {columna: None for columna in excel.COLUMNAS_ASPEL}
    fila.update(
        {
            "Clave Artículo": "ABC123",
            "Fecha de última compra": "04-08-2026",
            "PROVEEDOR": "Proveedor",
        }
    )
    ruta = excel.guardar_en_base_acumulada(pd.DataFrame([fila, fila]), str(tmp_path))

    base = pd.read_excel(ruta, header=1)
    assert len(base) == 1
