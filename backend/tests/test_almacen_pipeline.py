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
    assert excel._formatea_fecha("2026-08-04T00:00:00") == "04/08/2026"

    fila = {columna: None for columna in excel.COLUMNAS_ASPEL}
    fila.update(
        {
            "Clave Artículo": "ABC123",
            "Fecha de última compra": "04-08-2026",
            "PROVEEDOR": "Proveedor",
        }
    )
    ruta = excel.guardar_en_base_acumulada(pd.DataFrame([fila, fila]), str(tmp_path))

    base = pd.read_excel(ruta, header=0)
    assert len(base) == 1


def test_extraer_numero_proveedor() -> None:
    texto_makronix = "Proveedor:    (     463    )\nMAKRONIX"
    texto_universal = "Proveedor:    (     472    )\nUNIVERSAL FITTINGS"
    texto_scrambled = "MAKRONIX\n( 463 )\nProveedor: COMPRA"

    assert apoyo.extraer_numero_proveedor(texto_makronix) == "463"
    assert apoyo.extraer_numero_proveedor(texto_universal) == "472"
    assert apoyo.extraer_numero_proveedor(texto_scrambled) == "463"


def test_apoyo_txt_columnas_fijas_clave_con_espacio(tmp_path: Path) -> None:
    ruta = tmp_path / "1866.txt"
    contenido = (
        "Proveedor: ( 463 ) MAKRONIX\n"
        "       1.00         2460N 1                           GEN     FILTRO Y INOX 316 PTFE 1\"               0.00      1,250.00      1,250.00\n"
        "       2.00         3302N 1           40142505  H87   GEN     FILTRO Y LATON ROSCA NPT 1\"             0.00        450.00        900.00\n"
    )
    ruta.write_text(contenido, encoding="utf-8")

    resultado = apoyo.obtener_apoyo_por_folio(str(tmp_path), "2026", 1866)

    assert len(resultado) == 2
    assert resultado[0]["clave_articulo"] == "2460N 1"
    assert resultado[0]["linea"] == "GEN"
    assert resultado[0]["numero_proveedor"] == "463"
    assert resultado[1]["clave_articulo"] == "3302N 1"
    assert resultado[1]["linea"] == "GEN"
    assert resultado[1]["numero_proveedor"] == "463"


def _crear_xml_cfdi(ruta_xml: Path, folio: str, conceptos: list[tuple[str, str, float, float]]) -> None:
    nodos_concepto = "\n".join(
        f'    <cfdi:Concepto NoIdentificacion="{codigo}" Cantidad="{cantidad:.2f}" '
        f'ClaveUnidad="H87" ClaveProdServ="40142505" Descripcion="{descripcion}" '
        f'ValorUnitario="{precio:.2f}" Importe="{cantidad * precio:.2f}" Descuento="0.00"/>'
        for codigo, descripcion, cantidad, precio in conceptos
    )
    contenido = f"""<?xml version="1.0" encoding="UTF-8"?>
<cfdi:Comprobante xmlns:cfdi="http://www.sat.gob.mx/cfd/4"
                  Fecha="2026-10-30T12:00:00"
                  Folio="{folio}">
  <cfdi:Emisor Nombre="PROVEEDOR DEMO SA DE CV"/>
  <cfdi:Conceptos>
{nodos_concepto}
  </cfdi:Conceptos>
</cfdi:Comprobante>
"""
    ruta_xml.write_text(contenido, encoding="utf-8")


def test_duplicado_con_regalo_conserva_precio_mayor_en_ambos_ordenes(tmp_path: Path) -> None:
    import json

    for sufijo, precios in (("normal_primero", [20.66, 0.01]), ("regalo_primero", [0.01, 20.66])):
        carpeta = tmp_path / sufijo
        carpeta.mkdir(parents=True, exist_ok=True)
        _crear_xml_cfdi(
            carpeta / "FAC1901.xml",
            folio="1901",
            conceptos=[
                ("PC10-04", "CONECTOR RECTO MACHO 10MM", 10.0, precios[0]),
                ("PC10-04", "CONECTOR RECTO MACHO 10MM PROMO", 1.0, precios[1]),
            ],
        )
        (carpeta / "1901.txt").write_text(
            "Proveedor: ( 463 ) PROVEEDOR DEMO\n"
            "10.00 PC10-04 GEN CONECTOR RECTO MACHO 10MM\n"
            "1.00 PC10-04 GEN CONECTOR RECTO MACHO 10MM PROMO\n",
            encoding="utf-8",
        )

        excel.procesar_carpeta(str(carpeta))
        ruta_excel = carpeta / excel.NOMBRE_ARCHIVO_BASE
        assert ruta_excel.is_file()

        df = pd.read_excel(ruta_excel, header=0)
        assert len(df) == 1
        fila = df.iloc[0]
        assert fila["Clave Artículo"] == "PC10-04"
        assert float(fila["PRECIO COMPRA"]) == 20.66
        assert float(fila["PUBLICO"]) > 20.66

        resumen = json.loads((carpeta / excel.NOMBRE_ARCHIVO_RESUMEN).read_text(encoding="utf-8"))
        assert resumen["duplicados_ignorados"] == 1
        assert resumen["productos_regalo_sin_precio"] == []
        assert "advertencia_productos_regalo" not in resumen


def test_producto_solo_regalo_se_agrega_y_genera_advertencia(tmp_path: Path) -> None:
    import json

    carpeta = tmp_path / "solo_regalo"
    carpeta.mkdir(parents=True, exist_ok=True)
    _crear_xml_cfdi(
        carpeta / "FAC1902.xml",
        folio="1902",
        conceptos=[
            ("PC10-04", "CONECTOR RECTO MACHO 10MM", 5.0, 20.66),
            ("PC10-01", "CONECTOR RECTO REGALO 10MM", 1.0, 0.01),
        ],
    )
    (carpeta / "1902.txt").write_text(
        "Proveedor: ( 463 ) PROVEEDOR DEMO\n"
        "5.00 PC10-04 GEN CONECTOR RECTO MACHO 10MM\n"
        "1.00 PC10-01 GEN CONECTOR RECTO REGALO 10MM\n",
        encoding="utf-8",
    )

    excel.procesar_carpeta(str(carpeta))
    ruta_excel = carpeta / excel.NOMBRE_ARCHIVO_BASE
    assert ruta_excel.is_file()

    df = pd.read_excel(ruta_excel, header=0)
    assert len(df) == 2
    codigos = set(df["Clave Artículo"].astype(str))
    assert codigos == {"PC10-04", "PC10-01"}

    resumen = json.loads((carpeta / excel.NOMBRE_ARCHIVO_RESUMEN).read_text(encoding="utf-8"))
    regalos = resumen.get("productos_regalo_sin_precio", [])
    assert len(regalos) == 1
    assert regalos[0]["clave_articulo"] == "PC10-01"
    assert regalos[0]["precio_compra"] == 0.01
    advertencia = resumen.get("advertencia_productos_regalo", "")
    assert "PC10-01" in advertencia
    assert "regalado" in advertencia.lower()
    assert "ajusta" in advertencia.lower()



