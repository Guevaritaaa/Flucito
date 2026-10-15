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
from app.services.almacen.factores import (
    COLUMNAS_FACTORES,
    calcular_precios_numericos,
    detectar_rollo_metros,
    generar_formulas_fila,
    recuperar_clave_truncada,
    resolver_linea,
)
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
_PATRON_FORMULA_DIVISION = re.compile(r"^=\s*(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)\s*$")
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


def _precio_con_descuento(c: dict) -> float:
    """
    En el CFDI, Descuento es el monto total de descuento del concepto (no porcentaje).
    Precio neto unitario = ValorUnitario - (Descuento / Cantidad)
    Si no hay Descuento, retorna ValorUnitario tal cual.
    """
    valor = c["valor_unitario"]
    descuento = c.get("descuento", 0) or 0
    cantidad = c.get("cantidad", 1) or 1
    if descuento > 0:
        valor = valor - (descuento / cantidad)
    return round(valor, 4)


def _buscar_decision_rollo(
    decisiones_rollos: dict[str, dict[str, object]] | None,
    *claves: str | None,
) -> dict[str, object]:
    """Busca la decisión de rollo/metros para una clave de artículo o comodín '*'."""
    if not decisiones_rollos:
        return {}
    mapa_upper = {str(k).strip().upper(): v for k, v in decisiones_rollos.items() if isinstance(v, dict)}
    for clave in claves:
        if clave:
            encontrada = mapa_upper.get(str(clave).strip().upper())
            if encontrada is not None:
                return encontrada
    return mapa_upper.get("*", {})


def _fila_desde_concepto(
    c: dict,
    dato: dict | None,
    num_proveedor: str | None = None,
    factores_elegidos: dict[str, str | None] | None = None,
    decisiones_rollos: dict[str, dict[str, object]] | None = None,
    meta_por_clave: dict[str, dict[str, object]] | None = None,
) -> dict:
    clave_apoyo = dato["clave_articulo"] if dato else None
    clave_xml = c.get("no_identificacion")
    clave_articulo = recuperar_clave_truncada(clave_apoyo, clave_xml) or clave_xml

    # descripción corta: la del pdf/txt si la encontramos, si no, cae a la del XML
    descripcion_corta = (dato.get("descripcion_corta") if dato else None) or c["descripcion"]
    proveedor = (
        (dato.get("numero_proveedor") if dato else None)
        or num_proveedor
        or c["proveedor_nombre"]
    )

    linea_raw = (dato["linea"] if dato else None) or ""
    info_linea = resolver_linea(
        linea_raw,
        proveedor=str(c.get("proveedor_nombre") or ""),
        descripcion=f"{c.get('descripcion') or ''} {descripcion_corta or ''}",
        factores_temporales=factores_elegidos,
    )
    linea = info_linea["linea_resuelta"] or ""
    factor_nombre = info_linea["factor"]

    clave_unidad = c["clave_unidad"]
    precio_compra_bruto = _precio_con_descuento(c)
    precio_compra = precio_compra_bruto
    divisor_metros: float | None = None

    info_rollo = detectar_rollo_metros(
        clave_unidad=clave_unidad,
        descripcion_xml=str(c.get("descripcion") or ""),
        descripcion_apoyo=str(descripcion_corta or ""),
    )
    decision_rollo = _buscar_decision_rollo(
        decisiones_rollos,
        clave_articulo,
        clave_apoyo,
        clave_xml,
    )
    if decision_rollo.get("cambiar_a_mtr") and str(clave_unidad or "").strip().upper() == "XRO":
        clave_unidad = "MTR"

    metros_detectados = decision_rollo.get("metros") or info_rollo.get("metros")
    if decision_rollo.get("dividir_entre_metros") and metros_detectados:
        try:
            metros_float = float(metros_detectados)
            if metros_float > 0:
                divisor_metros = metros_float
                precio_compra = round(precio_compra_bruto / metros_float, 4)
        except (TypeError, ValueError):
            divisor_metros = None

    precios = calcular_precios_numericos(factor_nombre, precio_compra)

    if meta_por_clave is not None and clave_articulo:
        meta_por_clave[str(clave_articulo)] = {
            "factor": factor_nombre,
            "precio_compra_bruto": precio_compra_bruto if divisor_metros else None,
            "divisor_metros": divisor_metros,
        }

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
        "Clave unidad": clave_unidad,
        "Con serie": "N",
        "Con lote": "N",
        "Con pedimento": "N",
        "Tipo de costeo": "P",
        "CLAVE ESQUEMA": 1,
        "PROVEEDOR": proveedor,
        "MONEDA": "1",
        "PRECIO COMPRA": precio_compra,
        "PUBLICO": precios["PUBLICO"],
        "MINIMO": precios["MINIMO"],
        "LIQUIDACION": 0,
        "MOSTRADOR": precios["MOSTRADOR"],
        "MAYOREO": precios["MAYOREO"],
        "DISTRIBUIDOR": precios["DISTRIBUIDOR"],
        "cero": 0,
        "Existencias": 0,
        "Fecha de última compra": _formatea_fecha(c["fecha_compra"]),
    }


def procesar_xml(
    ruta_xml: str,
    carpeta: str,
    factores_elegidos: dict[str, str | None] | None = None,
    decisiones_rollos: dict[str, dict[str, object]] | None = None,
) -> pd.DataFrame:
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

    meta_por_clave: dict[str, dict[str, object]] = {}
    filas = [
        _fila_desde_concepto(
            c,
            d,
            num_proveedor,
            factores_elegidos=factores_elegidos,
            decisiones_rollos=decisiones_rollos,
            meta_por_clave=meta_por_clave,
        )
        for c, d in zip(conceptos, datos)
    ]
    df = pd.DataFrame(filas, columns=COLUMNAS_ASPEL)
    df.attrs["meta_por_clave"] = meta_por_clave
    logger.info(
        "[%s] %s productos XML (apoyo: %s items, proveedor: %s)",
        os.path.basename(ruta_xml),
        len(df),
        len(apoyo) if apoyo else "NO encontrado",
        num_proveedor or "por nombre",
    )
    return df


def _cargar_base_existente(ruta: str) -> pd.DataFrame:
    if not os.path.exists(ruta):
        return pd.DataFrame(columns=COLUMNAS_ASPEL)
    # encabezados en fila 1, datos desde fila 2 (formato Aspel SAE)
    df = pd.read_excel(ruta, header=0)
    if df.empty:
        return df

    # Si openpyxl guardó fórmulas sin caché de Excel, recalculamos los valores numéricos
    try:
        wb = openpyxl.load_workbook(ruta, data_only=False)
        ws = wb.active
    except Exception:
        ws = None

    indice_col = {nombre: idx + 1 for idx, nombre in enumerate(COLUMNAS_ASPEL)}
    meta_por_clave: dict[str, dict[str, object]] = {}

    for idx in range(len(df)):
        fila_excel = idx + 2
        clave = str(df.at[idx, "Clave Artículo"] or "")
        linea = str(df.at[idx, "Línea"] or "") if pd.notna(df.at[idx, "Línea"]) else ""
        precio_compra = df.at[idx, "PRECIO COMPRA"]
        bruto: float | None = None
        divisor: float | None = None

        if ws is not None and "PRECIO COMPRA" in indice_col:
            valor_celda = ws.cell(row=fila_excel, column=indice_col["PRECIO COMPRA"]).value
            if isinstance(valor_celda, str):
                match_div = _PATRON_FORMULA_DIVISION.match(valor_celda)
                if match_div:
                    bruto = float(match_div.group(1))
                    divisor = float(match_div.group(2))
                    if pd.isna(precio_compra) and divisor > 0:
                        precio_compra = round(bruto / divisor, 4)
                        df.at[idx, "PRECIO COMPRA"] = precio_compra

        info_linea = resolver_linea(
            linea,
            proveedor=str(df.at[idx, "PROVEEDOR"] or ""),
            descripcion=str(df.at[idx, "DESCRIPCION"] or ""),
        )
        factor = info_linea["factor"]
        if factor and pd.notna(precio_compra):
            precios = calcular_precios_numericos(factor, float(precio_compra))
            for col in COLUMNAS_FACTORES:
                if col in df.columns and pd.isna(df.at[idx, col]):
                    df.at[idx, col] = precios[col]

        if clave:
            meta_por_clave[clave] = {
                "factor": factor,
                "precio_compra_bruto": bruto,
                "divisor_metros": divisor,
            }

    df.attrs["meta_por_clave"] = meta_por_clave
    return df


def _aplicar_estilo(
    ruta: str,
    n_columnas: int,
    df_datos: pd.DataFrame | None = None,
    meta_por_clave: dict[str, dict[str, object]] | None = None,
) -> None:
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

    # Inyectar fórmulas dinámicas (=S{r}..., =T{r}...) en las columnas de precios
    if df_datos is not None and not df_datos.empty:
        indice_col = {
            str(ws.cell(row=1, column=col_idx).value or ""): col_idx
            for col_idx in range(1, n_columnas + 1)
        }
        mapa_meta = meta_por_clave or {}
        for idx, (_, fila) in enumerate(df_datos.iterrows()):
            fila_excel = idx + 2
            clave = str(fila.get("Clave Artículo") or "")
            meta_item = mapa_meta.get(clave, {})
            factor = meta_item.get("factor")
            if factor is None:
                linea_fila = fila.get("Línea")
                if pd.notna(linea_fila) and str(linea_fila).strip():
                    factor = resolver_linea(
                        str(linea_fila),
                        proveedor=str(fila.get("PROVEEDOR") or ""),
                        descripcion=str(fila.get("DESCRIPCION") or ""),
                    )["factor"]

            formulas = generar_formulas_fila(
                factor_nombre=str(factor) if factor else None,
                fila_excel=fila_excel,
                precio_compra_bruto=(
                    float(meta_item["precio_compra_bruto"])
                    if meta_item.get("precio_compra_bruto") is not None
                    else None
                ),
                divisor_metros=(
                    float(meta_item["divisor_metros"])
                    if meta_item.get("divisor_metros") is not None
                    else None
                ),
            )
            for col_nombre, formula in formulas.items():
                col_idx = indice_col.get(col_nombre)
                if col_idx is not None:
                    ws.cell(row=fila_excel, column=col_idx, value=formula)

    wb.save(ruta)


def guardar_en_base_acumulada(
    df_nuevo: pd.DataFrame,
    carpeta: str = str(CARPETA_DATOS),
    limpiar_previos: bool = True,
    prefijo: str = "BASE_ENTRADAS_ALMACEN",
    guardar_resumen: bool = True,
) -> str:
    os.makedirs(carpeta, exist_ok=True)
    nombre_excel = f"{prefijo}.xlsx"
    ruta = os.path.join(carpeta, nombre_excel)

    if limpiar_previos:
        existente = pd.DataFrame(columns=COLUMNAS_ASPEL)
        logger.info("Modo limpio: ignorando base anterior. Se generará un archivo nuevo.")
    else:
        existente = _cargar_base_existente(ruta)

    meta_combinada: dict[str, dict[str, object]] = {}
    if isinstance(existente.attrs.get("meta_por_clave"), dict):
        meta_combinada.update(existente.attrs["meta_por_clave"])
    if isinstance(df_nuevo.attrs.get("meta_por_clave"), dict):
        meta_combinada.update(df_nuevo.attrs["meta_por_clave"])

    combinado = pd.concat([existente, df_nuevo], ignore_index=True)
    antes = len(combinado)
    combinado.drop_duplicates(subset=CLAVES_DEDUPE, keep="last", inplace=True)
    combinado.reset_index(drop=True, inplace=True)
    duplicados_ignorados = antes - len(combinado)
    if duplicados_ignorados:
        logger.info("%s fila(s) duplicada(s) ignorada(s)", duplicados_ignorados)

    # Primero exportamos el DataFrame numérico y escribimos fórmulas dinámicas en el .xlsx
    combinado.to_excel(ruta, index=False)
    _aplicar_estilo(ruta, len(COLUMNAS_ASPEL), df_datos=combinado, meta_por_clave=meta_combinada)

    if guardar_resumen:
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

    # Generar TXT para importación Aspel SAE (comas y tabulaciones) con valores numéricos
    generar_ambos_txt(combinado, carpeta, prefijo)

    return ruta


def procesar_carpeta(
    carpeta: str = str(CARPETA_DATOS),
    factores_elegidos: dict[str, str | None] | None = None,
    decisiones_rollos: dict[str, dict[str, object]] | None = None,
) -> None:
    xmls = [
        os.path.join(carpeta, nombre)
        for nombre in os.listdir(carpeta)
        if os.path.splitext(nombre)[1].lower() == ".xml"
    ]
    if not xmls:
        logger.info("No hay XML en %s", carpeta)
        return

    dfs = []
    meta_total: dict[str, dict[str, object]] = {}
    for ruta_xml in xmls:
        try:
            if factores_elegidos is None and decisiones_rollos is None:
                df_xml = procesar_xml(ruta_xml, carpeta)
            else:
                df_xml = procesar_xml(
                    ruta_xml,
                    carpeta,
                    factores_elegidos=factores_elegidos,
                    decisiones_rollos=decisiones_rollos,
                )
            if isinstance(df_xml.attrs.get("meta_por_clave"), dict):
                meta_total.update(df_xml.attrs["meta_por_clave"])
            dfs.append(df_xml)
        except Exception as error:
            logger.exception("[%s] ERROR al procesar XML: %s", os.path.basename(ruta_xml), error)

    if dfs:
        df_nuevo = pd.concat(dfs, ignore_index=True)
        df_nuevo.attrs["meta_por_clave"] = meta_total
        guardar_en_base_acumulada(df_nuevo, carpeta)


__all__ = [
    "COLUMNAS_ASPEL",
    "CARPETA_DATOS",
    "NOMBRE_ARCHIVO_RESUMEN",
    "guardar_en_base_acumulada",
    "procesar_carpeta",
    "procesar_xml",
]
