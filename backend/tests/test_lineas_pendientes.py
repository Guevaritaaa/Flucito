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
