"""
Genera/actualiza la BASE DE ENTRADAS DE ALMACÉN: un solo Excel acumulativo
(no uno por factura). Cada corrida agrega lo nuevo y se sobreescribe el
mismo archivo. Emparejamiento XML <-> pdf/txt de apoyo por folio real.
Modo borrador: sin diccionario de mapeo interno ni factores de precio todavía.
"""

from __future__ import annotations

import logging
import os
import re

import openpyxl
import pandas as pd
from openpyxl.styles import Alignment, Font, PatternFill

from app.services.almacen.apoyo import buscar_dato, obtener_apoyo_por_folio
from app.services.almacen.extractor import CARPETA_DATOS, extraer_conceptos, leer_meta
from app.services.almacen.resumen import construir_resumen, guardar_resumen_json
from app.services.almacen.txt_aspel import generar_ambos_txt


COLUMNAS_ASPEL = [
    "ESTATUS", "Clave Artículo", "TIPO ELE", "DESCRIPCION", "Descripción CFDI",
    "Unidad de entrada", "Unidad de salida", "Peso nc", "Línea", "Clave SAT",
    "Clave unidad", "Con serie", "Con lote", "Con pedimento", "Tipo de costeo",
    "CLAVE ESQUEMA", "PROVEEDOR", "MONEDA", "PRECIO COMPRA", "PUBLICO",
    "MINIMO", "LIQUIDACION", "MOSTRADOR", "MAYOREO", "DISTRIBUIDOR",
    "cero", "Existencias", "Fecha de última compra",
]

COLOR_HEADER = "1F3864"  # azul marino, como tu plantilla
NOMBRE_ARCHIVO_BASE = "BASE_ENTRADAS_ALMACEN.xlsx"
NOMBRE_ARCHIVO_RESUMEN = "BASE_ENTRADAS_ALMACEN_RESUMEN.json"

# clave para no duplicar el mismo producto si vuelves a correr el script
# Al ser catálogo de inventario, la Clave Artículo debe ser estrictamente única.
# Si se vuelve a procesar el mismo producto, se actualiza costo y fecha (keep='last').
CLAVES_DEDUPE = ["Clave Artículo"]

PATRON_FECHA_CFDI = re.compile(r"^(\d{4})-(\d{2})-(\d{2})")
logger = logging.getLogger(__name__)


def _formatea_fecha(fecha_iso: str) -> str | None:
    """CFDI 4.0 siempre trae Fecha como AAAA-MM-DDTHH:MM:SS -> la pasamos a DD-MM-AAAA."""
    if not fecha_iso:
        return None
    m = PATRON_FECHA_CFDI.match(fecha_iso)
    if not m:
        return fecha_iso  # no debería pasar en un CFDI válido, pero no truena
    anio, mes, dia = m.groups()
    return f"{dia}/{mes}/{anio}"


def _fila_desde_concepto(c: dict, dato: dict | None, num_proveedor: str | None = None) -> dict:
    clave_articulo = dato["clave_articulo"] if dato else c["no_identificacion"]
    linea = (dato["linea"] if dato else None) or ""
    # descripción corta: la del pdf/txt si la encontramos, si no, cae a la del XML
    descripcion_corta = (dato.get("descripcion_corta") if dato else None) or c["descripcion"]
    proveedor = (
        (dato.get("numero_proveedor") if dato else None)
        or num_proveedor
        or c["proveedor_nombre"]
    )

    return {
        "ESTATUS": "A",
        "Clave Artículo": clave_articulo,
        "TIPO ELE": "P",
        "DESCRIPCION": descripcion_corta,
        "Descripción CFDI": c["descripcion"],
        "Unidad de entrada": "pza",
        "Unidad de salida": "pza",
        "Peso nc": 0,
        "Línea": linea,
        "Clave SAT": c["clave_prod_serv"],
        "Clave unidad": c["clave_unidad"],
        "Con serie": "N",
        "Con lote": "N",
        "Con pedimento": "N",
        "Tipo de costeo": "P",
        "CLAVE ESQUEMA": 1,
        "PROVEEDOR": proveedor,
        "MONEDA": "1",
        "PRECIO COMPRA": c["valor_unitario"],
        "PUBLICO": 0,
        "MINIMO": 0,
        "LIQUIDACION": 0,
        "MOSTRADOR": 0,
        "MAYOREO": 0,
        "DISTRIBUIDOR": 0,
        "cero": 0,
        "Existencias": 0,
        "Fecha de última compra": _formatea_fecha(c["fecha_compra"]),
    }


def procesar_xml(ruta_xml: str, carpeta: str) -> pd.DataFrame:
    """Un XML -> DataFrame con sus productos (todavía no escribe a disco)."""
    conceptos = extraer_conceptos(ruta_xml)
    meta = leer_meta(ruta_xml)

    apoyo = []
    if meta["folio"] is not None and meta["year"]:
        apoyo = obtener_apoyo_por_folio(carpeta, meta["year"], meta["folio"], rfc_proveedor=meta.get("rfc"))

    datos = [
        buscar_dato(apoyo, c["no_identificacion"]) or buscar_dato(apoyo, c["codigo_secundario"])
        for c in conceptos
    ]

    # el proveedor a veces usa un formato de código totalmente distinto en el
    # pdf/txt (visto con Universal Fittings: "UQ62-DOT-06" en xml vs "D62-06"
    # en pdf). Si el match por código falló para TODO el archivo y el total
    # de filas coincide, se asume mismo orden en ambos y se empareja por posición.
    if apoyo and all(d is None for d in datos) and len(apoyo) == len(conceptos):
        logger.warning(
            "[%s] match por código falló para todo; uso orden posicional "
            "(%s filas en ambos)",
            os.path.basename(ruta_xml),
            len(conceptos),
        )
        datos = apoyo

    num_proveedor = next(
        (d.get("numero_proveedor") for d in apoyo if isinstance(d, dict) and d.get("numero_proveedor")),
        None,
    )

    filas = [_fila_desde_concepto(c, d, num_proveedor) for c, d in zip(conceptos, datos)]
    df = pd.DataFrame(filas, columns=COLUMNAS_ASPEL)
    logger.info(
        "[%s] %s productos (apoyo %s, proveedor: %s)",
        os.path.basename(ruta_xml),
        len(df),
        "encontrado" if apoyo else "NO encontrado",
        num_proveedor or "por nombre",
    )
    return df


def _cargar_base_existente(ruta: str) -> pd.DataFrame:
    if not os.path.exists(ruta):
        return pd.DataFrame(columns=COLUMNAS_ASPEL)
    # encabezados en fila 1, datos desde fila 2 (formato Aspel SAE)
    return pd.read_excel(ruta, header=0)


def _aplicar_estilo(ruta: str, n_columnas: int) -> None:
    wb = openpyxl.load_workbook(ruta)
    ws = wb.active
    if ws is None:
        return

    for col in range(1, n_columnas + 1):
        celda = ws.cell(row=1, column=col)
        celda.font = Font(bold=True, color="FFFFFF")
        celda.fill = PatternFill("solid", fgColor=COLOR_HEADER)
        celda.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 22

    ws.freeze_panes = "A2"

    for col_idx in range(1, n_columnas + 1):
        letra = ws.cell(row=1, column=col_idx).column_letter
        max_len = max(
            len(str(ws.cell(row=1, column=col_idx).value or "")),
            max((len(str(ws.cell(row=r, column=col_idx).value or ""))
                 for r in range(2, ws.max_row + 1)), default=0),
        )
        ws.column_dimensions[letra].width = min(max(max_len + 2, 10), 40)

    wb.save(ruta)


def guardar_en_base_acumulada(df_nuevo: pd.DataFrame, carpeta: str = str(CARPETA_DATOS), limpiar_previos: bool = True, prefijo: str = "BASE_ENTRADAS_ALMACEN") -> str:
    os.makedirs(carpeta, exist_ok=True)
    nombre_excel = f"{prefijo}.xlsx"
    ruta = os.path.join(carpeta, nombre_excel)
    
    if limpiar_previos:
        existente = pd.DataFrame(columns=COLUMNAS_ASPEL)
        logger.info("Modo limpio: ignorando base anterior. Se generará un archivo nuevo.")
    else:
        existente = _cargar_base_existente(ruta)

    combinado = pd.concat([existente, df_nuevo], ignore_index=True)
    antes = len(combinado)
    combinado.drop_duplicates(subset=CLAVES_DEDUPE, keep="last", inplace=True)
    duplicados_ignorados = antes - len(combinado)
    if duplicados_ignorados:
        logger.info("%s fila(s) duplicada(s) ignorada(s)", duplicados_ignorados)

    combinado.to_excel(ruta, index=False)
    _aplicar_estilo(ruta, len(COLUMNAS_ASPEL))
    
    nombre_json = f"{prefijo}_RESUMEN.json"
    ruta_json = os.path.join(carpeta, nombre_json)
    guardar_resumen_json(
        construir_resumen(
            filas_nuevas=df_nuevo,
            filas_acumuladas=combinado,
            duplicados_ignorados=duplicados_ignorados,
            nombre_excel=nombre_excel,
            nombre_json=nombre_json,
        ),
        ruta_json,
    )
    logger.info("Reporte guardado en %s (%s productos en total)", ruta, len(combinado))

    # Generar TXT para importación Aspel SAE (comas y tabulaciones)
    generar_ambos_txt(combinado, carpeta, prefijo)

    return ruta


def procesar_carpeta(carpeta: str = str(CARPETA_DATOS)) -> None:
    xmls = [
        os.path.join(carpeta, nombre)
        for nombre in os.listdir(carpeta)
        if os.path.splitext(nombre)[1].lower() == ".xml"
    ]
    if not xmls:
        logger.info("No hay XML en %s", carpeta)
        return

    dfs = []
    for ruta_xml in xmls:
        try:
            dfs.append(procesar_xml(ruta_xml, carpeta))
        except Exception as error:
            logger.exception("[%s] ERROR al procesar XML: %s", os.path.basename(ruta_xml), error)

    if dfs:
        df_nuevo = pd.concat(dfs, ignore_index=True)
        guardar_en_base_acumulada(df_nuevo, carpeta)


__all__ = [
    "COLUMNAS_ASPEL",
    "CARPETA_DATOS",
    "NOMBRE_ARCHIVO_RESUMEN",
    "guardar_en_base_acumulada",
    "procesar_carpeta",
    "procesar_xml",
]
