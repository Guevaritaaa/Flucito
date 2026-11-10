"""Pruebas unitarias y de integración para el catálogo maestro Aspel SAE y flujo directo DOCUMENTOS ENTRADA."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from app.agents import tools
from app.agents.tools import almacen_tools, consultar_almacen, generar_entradas_almacen
from app.core.config import settings
from app.services.almacen import excel
from app.services.almacen.catalogo_sae import (
    ajustar_clave_nueva_16_chars,
    buscar_articulo_sae,
    cargar_catalogo_sae,
    resolver_proveedor_sae,
)
from app.services.almacen.fuentes import google_drive_client, sincronizador
from app.services.almacen.fuentes.google_drive import MIME_CARPETA


def test_catalogo_sae_carga_indices_y_resuelve_exacto_alterna_compacto_y_prefijo() -> None:
    """Verifica la carga de catalogo_sae.json y los 4 niveles de búsqueda de artículos."""
    cat = cargar_catalogo_sae()
    assert cat["disponible"] is True
    assert len(cat["articulos_exactos"]) >= 21900
    assert len(cat["lineas"]) >= 79
    assert len(cat["proveedores"]) >= 500

    # 1. Coincidencia exacta en INVE02
    art_festo = buscar_articulo_sae("197385")
    assert art_festo is not None
    assert art_festo["cve_art"] == "197385"
    assert art_festo["linea"] == "FESTO"
    assert art_festo["origen_clave"] == "INVE02_EXACTO"

    # 2. Clave alterna en CVES_ALTER02 consciente del proveedor
    art_alt = buscar_articulo_sae("UQ62-DOT-04", cve_prov="472")
    assert art_alt is not None
    assert art_alt["cve_art"] == "D62-04"
    assert art_alt["origen_clave"] == "CVES_ALTER02"

    # 3. Coincidencia compacta (espacios/guiones) sin colisionar medidas fraccionarias (1/4 vs 14)
    art_comp = buscar_articulo_sae("9406 0808")
    assert art_comp is not None
    assert art_comp["cve_art"] == "9406-0808"
    assert art_comp["origen_clave"] == "INVE02_COMPACTO"

    # PU14TRANSBLUE no debe colisionar con PU1/4TRANS-BLUE
    assert buscar_articulo_sae("PU14TRANSBLUE") is None
    art_pu_frac = buscar_articulo_sae("PU1/4TRANS-BLUE")
    assert art_pu_frac is not None
    assert art_pu_frac["cve_art"] == "PU1/4TRANS-BLUE"

    # 4. Prefijo único resuelve, pero prefijo ambiguo con múltiples candidatos NO adivina arbitrariamente
    art_pref_unico = buscar_articulo_sae("CILIND")
    assert art_pref_unico is not None
    assert art_pref_unico["cve_art"] == "CILINDRONCO"
    assert art_pref_unico["origen_clave"] == "INVE02_PREFIJO_UNICO"

    # C12A22414 tiene múltiples candidatos en INVE02 (C12A22414-04040, C12A22414-04060, C12A22414-08080)
    assert buscar_articulo_sae("C12A22414") is None


def test_ajustar_clave_nueva_16_chars_evita_colision_de_truncamiento() -> None:
    """Verifica que dos claves nuevas >16 caracteres con mismo prefijo no colisionen al truncarse."""
    lote: dict[str, str] = {}
    c1, col1 = ajustar_clave_nueva_16_chars("ARTICULO-123456789", claves_usadas_lote=lote)
    c2, col2 = ajustar_clave_nueva_16_chars("ARTICULO-123456780", claves_usadas_lote=lote)

    assert len(c1) == 16
    assert len(c2) == 16
    assert c1 == "ARTICULO-1234567"
    assert col1 is False
    assert c2 != c1
    assert c2.endswith("780")
    assert col2 is True


def test_resolver_proveedor_sae_por_rfc_y_desambiguacion_parker_kuriyama() -> None:
    """Verifica la resolución de número de proveedor desde PROV02 por RFC y desambiguación."""
    # RFC único (Automotriz Zertuche -> 7)
    cve_aze, orig_aze = resolver_proveedor_sae("AZE841112TH6")
    assert cve_aze == "7"
    assert orig_aze == "PROV02_RFC_UNICO"

    # RFC compartido Parker (PHM870907PP0 -> 2 para PKCIC, 3 para PKRFC/PKRH)
    cve_pkcic, _ = resolver_proveedor_sae("PHM870907PP0", linea="PKCIC")
    assert cve_pkcic == "2"
    cve_pkrfc, _ = resolver_proveedor_sae("PHM870907PP0", linea="PKRFC")
    assert cve_pkrfc == "3"

    # RFC Kuriyama (KME050613BI0 -> 213)
    cve_kuri, _ = resolver_proveedor_sae("KME050613BI0", linea="KURIY")
    assert cve_kuri == "213"


def test_solo_xml_resuelto_por_sae_procesa_sin_preguntar_solo_xml_pero_respeta_linea_sin_factor(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """
    Verifica los dos casos críticos de la retroalimentación técnica:
    1) Carpeta Solo XML donde el 100% de artículos están en INVE02 con línea y factor conocido (FESTO)
       se procesa automáticamente sin pedir confirmación `solo_xml`, calculando fórmulas y trazabilidad.
    2) Carpeta Solo XML donde el artículo está en INVE02 pero su línea (MYPC) no tiene factor de precios
       omite la pregunta `solo_xml`, pero SÍ detiene el flujo con `lineas_sin_factor` para preguntar el factor.
    """
    monkeypatch.setattr(tools, "CARPETA_DATOS", tmp_path)
    monkeypatch.setattr(sincronizador, "CARPETA_DATOS", tmp_path)
    monkeypatch.setattr(excel, "CARPETA_DATOS", tmp_path)
    monkeypatch.setattr(almacen_tools.settings, "google_drive_folder_id", "")

    # Caso 1: Solo XML con artículo 197385 (en INVE02 -> línea FESTO -> factor FESTO)
    xml_festo = """<?xml version="1.0" encoding="utf-8"?>
<cfdi:Comprobante xmlns:cfdi="http://www.sat.gob.mx/cfd/4" Folio="9001" Fecha="2026-10-26T12:00:00">
  <cfdi:Emisor Nombre="FESTO PNEUMATIC SA" Rfc="FPN690729411"/>
  <cfdi:Conceptos>
    <cfdi:Concepto NoIdentificacion="197385" Descripcion="CONECTOR RAPIDO" ClaveProdServ="40142000" ClaveUnidad="H87" Cantidad="10" ValorUnitario="50.00" Importe="500.00"/>
  </cfdi:Conceptos>
</cfdi:Comprobante>"""
    (tmp_path / "festo_solo.xml").write_text(xml_festo, encoding="utf-8")

    resp_festo = json.loads(generar_entradas_almacen.invoke({}))
    assert resp_festo["ok"] is True
    assert resp_festo["reporte_generado"] is True
    assert resp_festo["resumen"]["lineas"] == ["FESTO"]
    prod_det = resp_festo["resumen"]["productos_detalle"][0]
    assert prod_det["clave_articulo"] == "197385"
    assert prod_det["trazabilidad_sae"]["origen_clave"] == "INVE02_EXACTO"
    assert prod_det["trazabilidad_sae"]["origen_linea"] == "INVE02"
    assert prod_det["precios_venta"]["publico"] == round(50.0 / 0.7, 2)

    # Caso 2: Solo XML con artículo PU1/4TRANS-BLUE (en INVE02 -> línea MYPC -> sin factor configurado)
    dir_mypc = tmp_path / "caso_mypc"
    dir_mypc.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(tools, "CARPETA_DATOS", dir_mypc)
    monkeypatch.setattr(sincronizador, "CARPETA_DATOS", dir_mypc)
    monkeypatch.setattr(excel, "CARPETA_DATOS", dir_mypc)

    xml_mypc = """<?xml version="1.0" encoding="utf-8"?>
<cfdi:Comprobante xmlns:cfdi="http://www.sat.gob.mx/cfd/4" Folio="9002" Fecha="2026-10-27T12:00:00">
  <cfdi:Emisor Nombre="MANGUERAS Y CONEXIONES" Rfc="AAA010101AAA"/>
  <cfdi:Conceptos>
    <cfdi:Concepto NoIdentificacion="PU1/4TRANS-BLUE" Descripcion="TUBO POLIURETANO 1/4" ClaveProdServ="40142000" ClaveUnidad="MTR" Cantidad="5" ValorUnitario="20.00" Importe="100.00"/>
  </cfdi:Conceptos>
</cfdi:Comprobante>"""
    (dir_mypc / "mypc_solo.xml").write_text(xml_mypc, encoding="utf-8")

    resp_mypc = json.loads(generar_entradas_almacen.invoke({}))
    assert resp_mypc["ok"] is True
    assert resp_mypc["reporte_generado"] is False
    assert resp_mypc["requiere_confirmacion"] is True
    assert resp_mypc["tipo_confirmacion"] == "lineas_sin_factor"
    assert any(item["linea"] == "MYPC" for item in resp_mypc["lineas_sin_factor"])


def test_flujo_directo_documentos_entrada_no_acumulativo_entre_fechas_y_sin_regresion(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """
    Verifica:
    1) Descubrimiento y procesamiento in-situ dentro de DOCUMENTOS ENTRADA/2026/MES/DD-MM-YYYY
       sin necesidad de ENTRADAS AL INVENTARIO y sin borrar las carpetas de fecha.
    2) Reportes NO acumulativos entre fechas distintas (25-09-2026 vs 30-10-2026):
       BASE_ENTRADAS_ALMACEN.xlsx contiene solo el reporte de la fecha más reciente (30-10-2026).
    3) Protección contra regresión de fecha: si ya existe BASE_ENTRADAS_ALMACEN.xlsx de 30-10-2026 y se
       procesa una carpeta atrasada (10-09-2026), se genera el reporte de 10-09-2026 en Drive pero
       BASE_ENTRADAS_ALMACEN.xlsx conserva el reporte de 30-10-2026.
    """
    monkeypatch.setattr(settings, "google_drive_folder_id", "root-drive")
    monkeypatch.setattr(sincronizador, "CARPETA_DATOS", tmp_path)
    monkeypatch.setattr(excel, "CARPETA_DATOS", tmp_path)
    monkeypatch.setattr(sincronizador, "crear_cliente_drive", lambda: object())
    monkeypatch.setattr(sincronizador, "buscar_carpeta_hija", lambda *a, **kw: None)

    xml_sep = """<?xml version="1.0" encoding="utf-8"?>
<cfdi:Comprobante xmlns:cfdi="http://www.sat.gob.mx/cfd/4" Folio="101" Fecha="2026-09-25T10:00:00">
  <cfdi:Emisor Nombre="FESTO PNEUMATIC SA" Rfc="FPN690729411"/>
  <cfdi:Conceptos>
    <cfdi:Concepto NoIdentificacion="197385" Descripcion="CONECTOR RAPIDO" ClaveProdServ="40142000" ClaveUnidad="H87" Cantidad="2" ValorUnitario="50.00" Importe="100.00"/>
  </cfdi:Conceptos>
</cfdi:Comprobante>""".encode("utf-8")

    xml_oct = """<?xml version="1.0" encoding="utf-8"?>
<cfdi:Comprobante xmlns:cfdi="http://www.sat.gob.mx/cfd/4" Folio="202" Fecha="2026-10-30T10:00:00">
  <cfdi:Emisor Nombre="PARKER HANNIFIN DE MEXICO" Rfc="PHM870907PP0"/>
  <cfdi:Conceptos>
    <cfdi:Concepto NoIdentificacion="1.25RSR3.00" Descripcion="CILINDRO NEUMATICO" ClaveProdServ="27131701" ClaveUnidad="H87" Cantidad="4" ValorUnitario="80.00" Importe="320.00"/>
    <cfdi:Concepto NoIdentificacion="5727940220" Descripcion="VALVULA DIRECCIONAL" ClaveProdServ="40141603" ClaveUnidad="H87" Cantidad="1" ValorUnitario="900.00" Importe="900.00"/>
  </cfdi:Conceptos>
</cfdi:Comprobante>""".encode("utf-8")

    estructura_drive = {
        "root-drive": [
            {"id": "doc-ent", "name": "DOCUMENTOS ENTRADA", "mimeType": MIME_CARPETA},
        ],
        "doc-ent": [
            {"id": "y-2026", "name": "2026", "mimeType": MIME_CARPETA},
        ],
        "y-2026": [
            {"id": "m-sep", "name": "SEPTIEMBRE", "mimeType": MIME_CARPETA},
            {"id": "m-oct", "name": "OCTUBRE", "mimeType": MIME_CARPETA},
        ],
        "m-sep": [
            {"id": "f-25-09", "name": "25-09-2026", "mimeType": MIME_CARPETA},
        ],
        "m-oct": [
            {"id": "f-30-10", "name": "30-10-2026", "mimeType": MIME_CARPETA},
        ],
        "f-25-09": [
            {"id": "xml-sep-id", "name": "festo_sep.xml", "mimeType": "text/xml", "modifiedTime": "v1"},
        ],
        "f-30-10": [
            {"id": "xml-oct-id", "name": "festo_oct.xml", "mimeType": "text/xml", "modifiedTime": "v1"},
        ],
    }
    contenidos = {
        "festo_sep.xml": xml_sep,
        "festo_oct.xml": xml_oct,
    }
    subidos: list[tuple[str, str]] = []
    eliminados: list[str] = []

    monkeypatch.setattr(
        google_drive_client,
        "_listar_hijos",
        lambda _c, cid: list(estructura_drive.get(cid, [])),
    )
    monkeypatch.setattr(
        sincronizador,
        "buscar_o_crear_carpeta",
        lambda _c, nombre, padre: f"sub-{nombre}-{padre}",
    )
    monkeypatch.setattr(
        sincronizador,
        "descargar_archivo",
        lambda _c, arch, destino: destino.write_bytes(contenidos[arch.nombre]),
    )
    monkeypatch.setattr(google_drive_client, "mover_archivo", lambda *a, **kw: None)
    monkeypatch.setattr(
        google_drive_client,
        "subir_archivo",
        lambda _c, ruta, cid: subidos.append((Path(ruta).name, cid)),
    )
    monkeypatch.setattr(
        google_drive_client,
        "eliminar_archivo",
        lambda _c, fid: eliminados.append(fid),
    )

    res = sincronizador.sincronizar_drive(interactivo=True)
    assert res["carpetas_nuevas"] == 2
    assert res["fecha_reporte_base"] == "30-10-2026"
    assert res["productos"] == 2  # Solo los 2 productos del 30-10-2026, NO acumulados con 25-09-2026
    assert "f-25-09" not in eliminados
    assert "f-30-10" not in eliminados
    assert ("ENTRADAS_ALMACEN_25-09-2026.xlsx", "f-25-09") in subidos
    assert ("ENTRADAS_ALMACEN_30-10-2026.xlsx", "f-30-10") in subidos

    df_base = pd.read_excel(tmp_path / "BASE_ENTRADAS_ALMACEN.xlsx")
    assert set(df_base["Clave Artículo"].astype(str)) == {"1.25RSR3.00", "5727940220"}

    # Ahora simular que se sube una carpeta atrasada (10-09-2026) mientras ya existe el reporte del 30-10-2026
    estructura_drive["m-sep"].append(
        {"id": "f-10-09", "name": "10-09-2026", "mimeType": MIME_CARPETA}
    )
    estructura_drive["f-10-09"] = [
        {"id": "xml-10-sep-id", "name": "festo_10sep.xml", "mimeType": "text/xml", "modifiedTime": "v1"},
    ]
    contenidos["festo_10sep.xml"] = xml_sep

    res_atrasada = sincronizador.sincronizar_drive(interactivo=True)
    assert res_atrasada["carpetas_nuevas"] == 1
    assert ("ENTRADAS_ALMACEN_10-09-2026.xlsx", "f-10-09") in subidos

    # BASE_ENTRADAS_ALMACEN.xlsx NO debe haber retrocedido a 10-09-2026; sigue con 30-10-2026
    df_base_despues = pd.read_excel(tmp_path / "BASE_ENTRADAS_ALMACEN.xlsx")
    assert set(df_base_despues["Clave Artículo"].astype(str)) == {"1.25RSR3.00", "5727940220"}


def test_consultar_almacen_modo_catalogo_sae() -> None:
    """Verifica que consultar_almacen(tipo_consulta='catalogo_sae') consulte artículos, líneas y proveedores e incluya nota de alcance."""
    resp = json.loads(
        consultar_almacen.invoke(
            {
                "tipo_consulta": "catalogo_sae",
                "producto_o_clave": "197385",
                "linea": "FESTO",
            }
        )
    )
    assert resp["ok"] is True
    assert resp["tipo_consulta"] == "catalogo_sae"
    assert resp["disponible"] is True
    assert "no existencias físicas" in resp["alcance"]
    assert resp["total_articulos_coincidentes"] >= 1
    assert resp["articulos"][0]["cve_art"] == "197385"
    assert resp["linea_info"]["cve_lin"] == "FESTO"


def test_procesar_carpeta_local_multiples_fechas_no_acumula_entre_dias(tmp_path: Path) -> None:
    """Verifica que procesar_carpeta procese subcarpetas DD-MM-YYYY por separado y deje solo la más reciente en BASE_ENTRADAS_ALMACEN.xlsx."""
    d_sep = tmp_path / "25-09-2026"
    d_oct = tmp_path / "30-10-2026"
    d_sep.mkdir()
    d_oct.mkdir()

    (d_sep / "fac_sep.xml").write_text(
        '<cfdi:Comprobante xmlns:cfdi="http://www.sat.gob.mx/cfd/4" Folio="10" Fecha="2026-09-25T10:00:00">'
        '<cfdi:Emisor Nombre="FESTO" Rfc="FPN710301GQ3"/>'
        '<cfdi:Conceptos><cfdi:Concepto NoIdentificacion="197385" Descripcion="CONECTOR" ClaveProdServ="40142000" ClaveUnidad="H87" Cantidad="1" ValorUnitario="50.00" Importe="50.00"/></cfdi:Conceptos>'
        "</cfdi:Comprobante>",
        encoding="utf-8",
    )
    (d_oct / "fac_oct.xml").write_text(
        '<cfdi:Comprobante xmlns:cfdi="http://www.sat.gob.mx/cfd/4" Folio="20" Fecha="2026-10-30T10:00:00">'
        '<cfdi:Emisor Nombre="PARKER" Rfc="PHM870907PP0"/>'
        '<cfdi:Conceptos><cfdi:Concepto NoIdentificacion="1.25RSR3.00" Descripcion="CILINDRO" ClaveProdServ="27131701" ClaveUnidad="H87" Cantidad="2" ValorUnitario="120.00" Importe="240.00"/></cfdi:Conceptos>'
        "</cfdi:Comprobante>",
        encoding="utf-8",
    )

    excel.procesar_carpeta(str(tmp_path))

    assert (d_sep / "ENTRADAS_ALMACEN_25-09-2026.xlsx").is_file()
    assert (d_oct / "ENTRADAS_ALMACEN_30-10-2026.xlsx").is_file()

    df_base = pd.read_excel(tmp_path / "BASE_ENTRADAS_ALMACEN.xlsx")
    assert list(df_base["Clave Artículo"].astype(str)) == ["1.25RSR3.00"]

    resumen = json.loads((tmp_path / "BASE_ENTRADAS_ALMACEN_RESUMEN.json").read_text(encoding="utf-8"))
    assert resumen["fecha_reporte_base"] == "30-10-2026"
    assert resumen["fechas_procesadas_en_corrida"] == ["25-09-2026", "30-10-2026"]

