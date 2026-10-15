"""Pruebas unitarias para el módulo de factores de precios y autocorrección de líneas."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.almacen.factores import (
    CATALOGO_FACTORES,
    CATALOGO_LINEAS_BASE,
    SIN_FACTOR,
    calcular_precios_numericos,
    cargar_factores_personalizados,
    detectar_rollo_metros,
    formatear_menu_factores,
    generar_formulas_fila,
    guardar_factor_personalizado,
    normalizar_eleccion_factor,
    recuperar_clave_truncada,
    resolver_linea,
)


def test_catalogo_base_tiene_8_factores_y_76_lineas() -> None:
    assert len(CATALOGO_FACTORES) == 8
    assert len(CATALOGO_LINEAS_BASE) == 76
    assert CATALOGO_LINEAS_BASE["FESTO"]["factor"] == "FESTO"
    assert CATALOGO_LINEAS_BASE["CYB"]["factor"] == "CYBERMATIC"
    assert CATALOGO_LINEAS_BASE["DAYCO"]["factor"] is None


@pytest.mark.parametrize(
    ("linea_raw", "proveedor", "descripcion", "esperada", "factor_esperado"),
    [
        ("FEST", "FESTO PNEUMATIC SA", "CILINDRO", "FESTO", "FESTO"),
        ("ADC", "ADCCOM", "CONECTOR", "ADCCO", "COMPRAS GENERALES FORANEAS"),
        ("GEN", "GENEBRE", "VALVULA", "GENEB", "COMPRAS GENERALES FORANEAS"),
        ("KRUIY", "KURIYAMA", "MANGUERA", "KURIY", None),
        ("PKR", "PARKER FLUID", "MANGUERA HIDRAULICA", "PKRFC", "COMPRAS GENERALES FORANEAS"),
        ("PKR", "PARKER", "ELEMENTO FILTRANTE", "PKRF", "COMPRAS GENERALES FORANEAS"),
        ("VAR", "PROVEEDOR", "CABLE ELECTRICO", "VAREL", "COMPRAS GENERALES FORANEAS"),
        ("MAN", "DEWIT", "MANOMETRO GLICERINA 100 PSI", "MANOM", None),
        ("VAY", "NUEVO PROV", "PRODUCTO NUEVO", "VAY", None),
    ],
)
def test_resolver_linea_autocorrige_codigos_truncados(
    linea_raw: str,
    proveedor: str,
    descripcion: str,
    esperada: str,
    factor_esperado: str | None,
    tmp_path: Path,
) -> None:
    ruta_json = tmp_path / "FACTORES_PERSONALIZADOS.json"
    resultado = resolver_linea(
        linea_raw,
        proveedor=proveedor,
        descripcion=descripcion,
        ruta_personalizados=ruta_json,
    )
    assert resultado["linea_resuelta"] == esperada
    assert resultado["factor"] == factor_esperado


def test_guardar_y_cargar_factor_personalizado(tmp_path: Path) -> None:
    ruta_json = tmp_path / "FACTORES_PERSONALIZADOS.json"
    guardar_factor_personalizado(
        linea="DAYCO",
        factor="2",
        descripcion="DAYCO",
        ruta=ruta_json,
    )
    guardar_factor_personalizado(
        linea="VAY",
        factor="COMPRAS GENERALES LOCALES",
        descripcion="LINEA VAY",
        ruta=ruta_json,
    )

    guardados = cargar_factores_personalizados(ruta_json)
    assert guardados["DAYCO"]["factor"] == "COMPRAS GENERALES FORANEAS"
    assert guardados["VAY"]["factor"] == "COMPRAS GENERALES LOCALES"

    resuelto = resolver_linea("DAY", ruta_personalizados=ruta_json)
    assert resuelto["linea_resuelta"] == "DAYCO"
    assert resuelto["factor"] == "COMPRAS GENERALES FORANEAS"


def test_normalizar_eleccion_factor_y_menu() -> None:
    menu = formatear_menu_factores()
    assert "1. **COMPRAS GENERALES LOCALES**" in menu
    assert "8. **CYBERMATIC**" in menu
    assert "9. **Sin factor**" in menu

    assert normalizar_eleccion_factor(1) == "COMPRAS GENERALES LOCALES"
    assert normalizar_eleccion_factor("2") == "COMPRAS GENERALES FORANEAS"
    assert normalizar_eleccion_factor("8. CYBERMATIC") == "CYBERMATIC"
    assert normalizar_eleccion_factor("9") == SIN_FACTOR
    assert normalizar_eleccion_factor("sin factor") == SIN_FACTOR


def test_recuperar_clave_truncada_en_txt() -> None:
    assert recuperar_clave_truncada("PU14TRANSBLU", "PU14TRANSBLUE") == "PU14TRANSBLUE"
    assert recuperar_clave_truncada("65040806", "6504 08 06") == "65040806"
    assert recuperar_clave_truncada("", "ABC123") == "ABC123"


def test_detectar_rollo_metros() -> None:
    caso_cyber = detectar_rollo_metros(
        clave_unidad="XRO",
        descripcion_xml="(100m) Manguera de Poliuretano en Carret",
        descripcion_apoyo="MANGUERA POLIURETANO 10X6.5 AZUL TR",
    )
    assert caso_cyber["es_xro"] is True
    assert caso_cyber["metros"] == 100.0
    assert caso_cyber["requiere_confirmacion"] is True

    caso_pieza_normal = detectar_rollo_metros(
        clave_unidad="H87",
        descripcion_xml="Conector Recto Macho 10MM x 1/4 NPT",
        descripcion_apoyo="CONECTOR RECTO",
    )
    assert caso_pieza_normal["es_xro"] is False
    assert caso_pieza_normal["metros"] is None
    assert caso_pieza_normal["requiere_confirmacion"] is False


def test_calcular_precios_numericos_y_formulas_cybermatic() -> None:
    precios = calcular_precios_numericos("CYBERMATIC", 90.0)
    assert precios == {
        "PUBLICO": 200.0,
        "MINIMO": 160.0,
        "MOSTRADOR": 200.0,
        "MAYOREO": 180.0,
        "DISTRIBUIDOR": 160.0,
    }

    formulas = generar_formulas_fila(
        factor_nombre="CYBERMATIC",
        fila_excel=6,
        precio_compra_bruto=1796.3236,
        divisor_metros=100.0,
    )
    assert formulas == {
        "PRECIO COMPRA": "=1796.3236/100",
        "PUBLICO": "=S6/.9*2",
        "MINIMO": "=T6*.8",
        "MOSTRADOR": "=T6",
        "MAYOREO": "=T6*.9",
        "DISTRIBUIDOR": "=T6*.8",
    }


def test_excel_inyecta_formulas_dinamicas_y_txt_exporta_numeros(tmp_path: Path) -> None:
    import openpyxl
    import pandas as pd
    from app.services.almacen import excel

    concepto_rollo = {
        "no_identificacion": "PU14TRANSBLUE",
        "codigo_secundario": None,
        "descripcion": "(100m) Manguera de Poliuretano en Carret",
        "clave_prod_serv": "40142000",
        "clave_unidad": "XRO",
        "cantidad": 1.0,
        "valor_unitario": 1796.3236,
        "descuento": 0.0,
        "proveedor_nombre": "CYBERMATICS",
        "fecha_compra": "2026-08-04T12:00:00",
    }
    dato_txt_rollo = {
        "clave_articulo": "PU14TRANSBLU",  # truncado a 12 chars por SAE
        "linea": "CYB",
        "descripcion_corta": "MANGUERA POLIURETANO 10X6.5 AZUL TR",
        "numero_proveedor": "491",
    }

    meta_por_clave: dict[str, dict[str, object]] = {}
    fila = excel._fila_desde_concepto(
        concepto_rollo,
        dato_txt_rollo,
        decisiones_rollos={
            "PU14TRANSBLUE": {
                "cambiar_a_mtr": True,
                "dividir_entre_metros": True,
                "metros": 100.0,
            }
        },
        meta_por_clave=meta_por_clave,
    )

    assert fila["Clave Artículo"] == "PU14TRANSBLUE"
    assert fila["Clave unidad"] == "MTR"
    assert fila["Línea"] == "CYB"
    assert fila["PRECIO COMPRA"] == 17.9632
    assert fila["PUBLICO"] == round(17.9632 / 0.9 * 2, 4)

    df = pd.DataFrame([fila], columns=excel.COLUMNAS_ASPEL)
    df.attrs["meta_por_clave"] = meta_por_clave

    ruta_xlsx = excel.guardar_en_base_acumulada(df, str(tmp_path), prefijo="TEST_REPORTE")

    # 1. Verificar fórmulas dinámicas en el .xlsx
    wb = openpyxl.load_workbook(ruta_xlsx, data_only=False)
    ws = wb.active
    assert ws is not None
    encabezados = {ws.cell(row=1, column=c).value: c for c in range(1, ws.max_column + 1)}
    assert ws.cell(row=2, column=encabezados["PRECIO COMPRA"]).value == "=1796.3236/100"
    assert ws.cell(row=2, column=encabezados["PUBLICO"]).value == "=S2/.9*2"
    assert ws.cell(row=2, column=encabezados["MINIMO"]).value == "=T2*.8"
    assert ws.cell(row=2, column=encabezados["MOSTRADOR"]).value == "=T2"
    assert ws.cell(row=2, column=encabezados["MAYOREO"]).value == "=T2*.9"
    assert ws.cell(row=2, column=encabezados["DISTRIBUIDOR"]).value == "=T2*.8"

    # 2. Verificar valores numéricos en el TXT (sin fórmulas '=' ni NaN)
    ruta_txt_comas = tmp_path / "TEST_REPORTE_COMAS.txt"
    contenido_txt = ruta_txt_comas.read_text(encoding="utf-8")
    assert "=S2" not in contenido_txt
    assert "nan" not in contenido_txt.lower()
    assert "17.9632" in contenido_txt
    assert "39.9182" in contenido_txt

