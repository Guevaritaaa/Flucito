import pytest

from app.services.almacen import apoyo, excel
from app.services.almacen.procedencia import explicar_producto


@pytest.mark.parametrize("clave,prefijo", [("BW-SAF4000DME", "BW-"), ("PRUEBA-125AZ", "PRUEBA-")])
def test_explicacion_clave_truncada_es_general(monkeypatch, clave, prefijo):
    monkeypatch.setattr(excel, "_articulo_factura", lambda *a: {
        "cve_art": clave, "descr": "Producto", "linea": "", "origen_clave": "INVE02_EXACTO"})
    monkeypatch.setattr(excel, "inferir_linea_por_proveedor", lambda *a, **kw: (None, None))
    c = dict(no_identificacion=clave, descripcion="Producto", clave_unidad="H87", clave_prod_serv="40161526",
             valor_unitario=443.716, fecha_compra="2026-10-16", proveedor_nombre="Proveedor")
    dato = dict(clave_articulo=prefijo, linea=None)
    meta = {}
    excel._fila_desde_concepto(c, dato, meta_por_clave=meta)
    texto = explicar_producto(clave, meta[clave])
    assert f"incompleta en el TXT/PDF: {prefijo}" in texto
    assert f"El XML aporta {clave}" in texto
    assert "catálogo del SAE confirmó" in texto
    assert "columna de línea de esta partida está vacía" in texto
    assert "tampoco tiene línea en el catálogo del SAE" in texto


def test_apoyo_ilegible_no_se_describe_como_columna_vacia(monkeypatch, tmp_path):
    (tmp_path / "factura123.txt").write_text("ilegible")
    monkeypatch.setattr(apoyo, "_leer_desde_txt", lambda *a: [])
    leido = apoyo.obtener_apoyo_por_folio(str(tmp_path), "2026", 123)
    fuente = apoyo.fuentes_apoyo(leido, None)
    texto = explicar_producto("ABC", {"fuentes": {"apoyo": fuente}, "origen_linea": "SIN_LINEA"})
    assert fuente["estado"] == "LECTURA_FALLIDA"
    assert "no se puede afirmar" in texto
    assert "esta partida está vacía" not in texto


def test_sugerencias_conservan_modelo_medida_sat_unidad_y_agrupan(monkeypatch):
    from app.services.almacen import lineas
    def art(clave, linea="YPC", sat="40161526", unidad="H87"):
        return dict(cve_art=clave, descr=clave, linea=linea, cve_sat=sat, cve_unidad=unidad)
    items = [art("BW-SAF4000ME"), art("BW-SAF4000"), art("BW-SAF4000D", "OTRA"),
             art("BW-SAF5000"), art("BW-SAF4000X", sat="11111111"), art("BW-SAF4000Z", unidad="MTR")]
    monkeypatch.setattr(lineas, "cargar_catalogo_sae", lambda: {"articulos_exactos": {a["cve_art"]: a for a in items}})
    sugerencias = lineas.sugerir_lineas("BW-SAF4000DME", "40161526", "H87")
    assert {g["linea"] for g in sugerencias} == {"YPC", "OTRA"}
    assert sum(len(g["referencias"]) for g in sugerencias) == 3
    assert lineas._familia("PU1/4-A") != lineas._familia("PU14-A")
    assert lineas.sugerir_lineas("SINNUMERO", "40161526", "H87") == []
    with pytest.raises(ValueError):
        lineas.aplicar_decision("BW-SAF4000DME", "40161526", "H87", {
            "BW-SAF4000DME": {"linea": "YPC", "referencia": "BW-SAF4000ME"}})


def test_decision_linea_traduce_referencia_sin_recordarla():
    from app.services import decisiones
    i = decisiones.construir({"productos_sin_linea": [{"clave_articulo": "BW-SAF4000DME", "sugerencias": [{
        "linea": "YPC", "referencias": [{"cve_art": "BW-SAF4000ME", "descr": "Vaso sin purga", "linea": "YPC"}]}]}]},
        "generar_entradas_almacen", {}, None)
    assert i["preguntas"][0]["clave_preferencia"] is None
    i["respuestas"] = {"linea:BW-SAF4000DME": {"opcion": "linea:YPC"}}
    args, _ = decisiones.traducir({"interaccion": i, "argumentos": {}})
    assert args["decisiones_lineas"]["BW-SAF4000DME"] == {
        "linea": "YPC", "referencia": "BW-SAF4000ME", "confirmada": True}
