"""Construcción de resumen conversacional detallado para entradas de almacén."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import pandas as pd

from app.services.almacen.factores import calcular_precios_numericos, resolver_linea
from app.services.almacen.procedencia import explicar_producto


def _limpiar_numero(valor: Any, decimales: int = 4) -> float | None:
    """Convierte un valor numérico de pandas a float redondeado o None si es vacío/NaN."""
    if valor is None or pd.isna(valor):
        return None
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return None
    if pd.isna(numero):
        return None
    return round(numero, decimales)


def _limpiar_texto(valor: Any) -> str | None:
    """Normaliza un valor de celda a texto limpio o None si está vacío."""
    if valor is None or pd.isna(valor):
        return None
    texto = str(valor).strip()
    return texto if texto else None


def explicar_procedencia_reporte(resumen: dict[str, Any]) -> str:
    """Explica únicamente las decisiones cuya procedencia quedó registrada."""
    trazabilidad = resumen.get("trazabilidad_catalogo_sae") or {}
    detalles = resumen.get("productos_detalle") or []
    explicaciones = []
    motivos = {
        "origen_linea": {
            "INVE02": "tomé la línea del catálogo del SAE",
            "TXT_APOYO": "tomé la línea del TXT o PDF de apoyo",
            "HISTORIAL_UNICA": "usé la única línea registrada en el historial de compras de ese proveedor",
            "HISTORIAL_KEYWORD": "relacioné la descripción con una línea del historial de ese proveedor",
            "VARIANTE_INVE02": "usé la línea de artículos de la misma familia dimensional en el catálogo del SAE",
            "VARIANTE_MISMA_FACTURA": "usé la línea de otras medidas de la misma familia dentro de la factura",
        },
        "origen_clave": {
            "INVE02_EXACTO": "utilicé la clave que coincidía exactamente en el catálogo del SAE",
            "CVES_ALTER02": "relacioné el código con una clave alterna registrada en SAE",
            "INVE02_COMPACTO": "encontré una coincidencia única del código normalizado en el catálogo del SAE",
            "INVE02_PREFIJO_UNICO": "completé la clave con una coincidencia única por prefijo en el catálogo del SAE",
            "INVE02_PREFIJO_DESAMBIGUADO": "completé el prefijo de la clave de apoyo usando el código del XML para resolver la coincidencia",
            "TXT_APOYO": "utilicé la clave obtenida con el documento de apoyo",
            "XML": "utilicé el código obtenido del XML",
        },
    }
    for campo, origenes in motivos.items():
        for origen, motivo in origenes.items():
            cantidad = (trazabilidad.get(campo) or {}).get(origen, 0)
            if not cantidad:
                continue
            ejemplos = []
            for producto in detalles:
                if (producto.get("trazabilidad_sae") or {}).get(campo) != origen:
                    continue
                clave = producto.get("clave_articulo")
                valor = producto.get("linea") if campo == "origen_linea" else clave
                codigo = (producto.get("trazabilidad_sae") or {}).get("codigo_xml_original")
                ejemplo = f"{clave} → {valor}" if campo == "origen_linea" and valor else str(clave or "")
                if campo == "origen_clave" and codigo:
                    ejemplo = f"{codigo} → {clave}"
                if ejemplo and ejemplo not in ejemplos:
                    ejemplos.append(ejemplo)
                if len(ejemplos) == 2:
                    break
            muestra = f" Por ejemplo, {', '.join(ejemplos)}." if ejemplos else ""
            unidad = "producto" if cantidad == 1 else "productos"
            explicaciones.append(f"- En {cantidad} {unidad}, {motivo}.{muestra}")
    factores = [
        f"{item['linea']} con el factor {item['factor_aplicado']}"
        for item in resumen.get("desglose_por_linea", [])
        if item.get("factor_aplicado") and item["factor_aplicado"] not in ("SIN_FACTOR", "LLENADO_MANUAL")
    ]
    if factores:
        explicaciones.append("- Para los precios de venta apliqué los factores indicados en el reporte, "
                             + ", ".join(factores[:5])
                             + (f" y los de otras {len(factores) - 5} líneas." if len(factores) > 5 else "."))
    conversiones = resumen.get("conversiones_a_metros") or {}
    if conversiones:
        muestra_conversiones = list(conversiones.items())[:5]
        explicaciones.append("- Dividí el precio neto de compra entre los metros confirmados por rollo o tramo en "
                             + ", ".join(f"{clave} ({metros:g} m)" for clave, metros in muestra_conversiones)
                             + (f" y otros {len(conversiones) - 5} productos." if len(conversiones) > 5 else "."))
    duplicados = resumen.get("duplicados_ignorados", 0)
    if duplicados:
        filas = "fila repetida" if duplicados == 1 else "filas repetidas"
        explicaciones.append(f"- Consolidé {duplicados} {filas} por clave, conservando el precio de compra más alto.")
    sin_linea = resumen.get("productos_sin_linea")
    if isinstance(sin_linea, int) and sin_linea > 0:
        ejemplos = [str(p["clave_articulo"]) for p in detalles if p.get("clave_articulo") and not p.get("linea")][:5]
        muestra = f" Entre ellos: {', '.join(ejemplos)}." if ejemplos else ""
        explicaciones.append(
            f"- {sin_linea} producto(s) quedaron con la línea vacía y necesitan revisión antes de usar el reporte."
            + muestra
        )
    for caso in resumen.get("explicaciones_productos", []):
        explicaciones.append("- " + caso)
    if not explicaciones:
        return ""
    return "**Cómo se preparó este reporte**\n\n" + "\n".join(explicaciones)


def construir_resumen(
    filas_nuevas: pd.DataFrame,
    filas_acumuladas: pd.DataFrame | None = None,
    duplicados_ignorados: int = 0,
    nombre_excel: str = "BASE_ENTRADAS_ALMACEN.xlsx",
    nombre_json: str = "BASE_ENTRADAS_ALMACEN_RESUMEN.json",
    datos_sincronizacion: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Crea un resumen estructurado y completo para explicar el reporte Excel generado."""
    if filas_acumuladas is None:
        filas_acumuladas = filas_nuevas

    meta_por_clave = (
        filas_acumuladas.attrs.get("meta_por_clave", {})
        if isinstance(filas_acumuladas.attrs.get("meta_por_clave"), dict)
        else {}
    )
    proveedores = sorted(
        {
            str(valor).strip()
            for valor in filas_acumuladas.get("PROVEEDOR", [])
            if pd.notna(valor) and str(valor).strip()
        }
    )

    lineas_resueltas: set[str] = set()
    conteo_por_linea: dict[str, dict[str, Any]] = {}
    conteo_por_proveedor: dict[str, dict[str, Any]] = {}
    productos_detalle: list[dict[str, Any]] = []

    precios_compra_validos: list[float] = []
    productos_con_precios_venta = 0
    productos_sin_precios_venta = 0
    conteo_origen_clave: dict[str, int] = {}
    conteo_origen_linea: dict[str, int] = {}
    conteo_origen_proveedor: dict[str, int] = {}
    conversiones_a_metros: dict[str, float] = {}
    productos_sin_linea = 0

    for _, fila in filas_acumuladas.iterrows():
        clave_articulo = _limpiar_texto(fila.get("Clave Artículo")) or ""
        descripcion = _limpiar_texto(fila.get("DESCRIPCION")) or ""
        meta_item = (
            meta_por_clave.get(clave_articulo, {})
            if isinstance(meta_por_clave.get(clave_articulo), dict)
            else {}
        )
        origen_clave = _limpiar_texto(meta_item.get("origen_clave"))
        origen_linea = _limpiar_texto(meta_item.get("origen_linea"))
        origen_proveedor = _limpiar_texto(meta_item.get("origen_proveedor"))
        codigo_xml_original = _limpiar_texto(meta_item.get("codigo_xml_original"))
        divisor_metros = _limpiar_numero(meta_item.get("divisor_metros"))
        if divisor_metros and divisor_metros > 0:
            conversiones_a_metros[clave_articulo] = divisor_metros

        if origen_clave:
            conteo_origen_clave[origen_clave] = conteo_origen_clave.get(origen_clave, 0) + 1
        if origen_linea:
            conteo_origen_linea[origen_linea] = conteo_origen_linea.get(origen_linea, 0) + 1
        if origen_proveedor:
            conteo_origen_proveedor[origen_proveedor] = (
                conteo_origen_proveedor.get(origen_proveedor, 0) + 1
            )
        descripcion_cfdi = _limpiar_texto(fila.get("Descripción CFDI")) or _limpiar_texto(
            meta_item.get("descripcion_cfdi")
        )
        proveedor = _limpiar_texto(fila.get("PROVEEDOR")) or "SIN PROVEEDOR"
        linea_raw = _limpiar_texto(fila.get("Línea")) or ""
        unidad = _limpiar_texto(fila.get("Clave unidad")) or _limpiar_texto(fila.get("Unidad de entrada"))
        moneda = _limpiar_texto(fila.get("MONEDA")) or "MXN"
        clave_sat = _limpiar_texto(fila.get("Clave SAT"))
        fecha_compra = _limpiar_texto(fila.get("Fecha de última compra"))

        info_linea = (
            resolver_linea(linea_raw, proveedor=proveedor, descripcion=descripcion)
            if linea_raw
            else {"linea_resuelta": None, "factor": None, "descripcion_linea": None}
        )
        linea_final = _limpiar_texto(info_linea.get("linea_resuelta")) or linea_raw or None
        if not linea_final:
            productos_sin_linea += 1
        factor_aplicado = (
            _limpiar_texto(meta_item.get("factor"))
            or _limpiar_texto(info_linea.get("factor"))
        )

        if linea_final:
            lineas_resueltas.add(linea_final)
            item_linea = conteo_por_linea.setdefault(
                linea_final,
                {
                    "linea": linea_final,
                    "descripcion_linea": info_linea.get("descripcion_linea") or linea_final,
                    "factor_aplicado": factor_aplicado,
                    "total_productos": 0,
                },
            )
            item_linea["total_productos"] += 1

        precio_compra = _limpiar_numero(fila.get("PRECIO COMPRA"))
        precio_publico = _limpiar_numero(fila.get("PUBLICO"), decimales=2)
        precio_minimo = _limpiar_numero(fila.get("MINIMO"), decimales=2)
        precio_liquidacion = _limpiar_numero(fila.get("LIQUIDACION"), decimales=2)
        precio_mostrador = _limpiar_numero(fila.get("MOSTRADOR"), decimales=2)
        precio_mayoreo = _limpiar_numero(fila.get("MAYOREO"), decimales=2)
        precio_distribuidor = _limpiar_numero(fila.get("DISTRIBUIDOR"), decimales=2)

        if (
            precio_publico is None
            and precio_compra is not None
            and precio_compra > 0
            and factor_aplicado
        ):
            calculados = calcular_precios_numericos(factor_aplicado, precio_compra)
            precio_publico = _limpiar_numero(calculados.get("PUBLICO"), decimales=2)
            precio_minimo = _limpiar_numero(calculados.get("MINIMO"), decimales=2)
            precio_liquidacion = _limpiar_numero(calculados.get("LIQUIDACION"), decimales=2)
            precio_mostrador = _limpiar_numero(calculados.get("MOSTRADOR"), decimales=2)
            precio_mayoreo = _limpiar_numero(calculados.get("MAYOREO"), decimales=2)
            precio_distribuidor = _limpiar_numero(calculados.get("DISTRIBUIDOR"), decimales=2)

        if precio_compra is not None and precio_compra > 0:
            precios_compra_validos.append(precio_compra)

        tiene_precios_venta = any(
            p is not None and p > 0
            for p in (precio_publico, precio_distribuidor, precio_minimo)
        )
        if tiene_precios_venta:
            productos_con_precios_venta += 1
        else:
            productos_sin_precios_venta += 1

        info_prov = conteo_por_proveedor.setdefault(
            proveedor,
            {
                "proveedor": proveedor,
                "total_productos": 0,
                "lineas": set(),
                "suma_precio_compra_unitario": 0.0,
            },
        )
        info_prov["total_productos"] += 1
        if linea_final:
            info_prov["lineas"].add(linea_final)
        if precio_compra is not None and precio_compra > 0:
            info_prov["suma_precio_compra_unitario"] = round(
                info_prov["suma_precio_compra_unitario"] + precio_compra, 4
            )

        if len(productos_detalle) < 50:
            detalle_prod: dict[str, Any] = {
                "clave_articulo": clave_articulo,
                "descripcion": descripcion,
                "descripcion_cfdi": (
                    descripcion_cfdi
                    if descripcion_cfdi and descripcion_cfdi != descripcion
                    else None
                ),
                "linea": linea_final,
                "factor": factor_aplicado,
                "unidad": unidad,
                "clave_sat": clave_sat,
                "proveedor": proveedor,
                "moneda": moneda,
                "precio_compra": precio_compra,
                "precios_venta": {
                    "publico": precio_publico,
                    "mostrador": precio_mostrador,
                    "mayoreo": precio_mayoreo,
                    "distribuidor": precio_distribuidor,
                    "minimo": precio_minimo,
                    "liquidacion": precio_liquidacion,
                },
                "fecha_ultima_compra": fecha_compra,
            }
            if origen_clave or origen_linea or origen_proveedor:
                detalle_prod["trazabilidad_sae"] = {
                    "origen_clave": origen_clave,
                    "origen_linea": origen_linea,
                    "origen_proveedor": origen_proveedor,
                    "codigo_xml_original": (
                        codigo_xml_original
                        if codigo_xml_original and codigo_xml_original != clave_articulo
                        else None
                    ),
                }
            productos_detalle.append(detalle_prod)

    lineas = sorted(lineas_resueltas)

    desglose_proveedores = [
        {
            "proveedor": item["proveedor"],
            "total_productos": item["total_productos"],
            "lineas": sorted(item["lineas"]),
            "suma_precio_compra_unitario": item["suma_precio_compra_unitario"],
        }
        for item in sorted(
            conteo_por_proveedor.values(),
            key=lambda x: (-x["total_productos"], x["proveedor"]),
        )
    ]

    desglose_lineas = sorted(
        conteo_por_linea.values(),
        key=lambda x: (-x["total_productos"], x["linea"]),
    )

    fechas = pd.to_datetime(
        filas_acumuladas.get("Fecha de última compra", pd.Series(dtype=str)),
        dayfirst=True,
        errors="coerce",
    ).dropna()

    estadisticas_precios = {
        "productos_con_precios_venta": productos_con_precios_venta,
        "productos_sin_precios_venta": productos_sin_precios_venta,
        "suma_precios_compra_unitarios": (
            round(sum(precios_compra_validos), 4) if precios_compra_validos else 0.0
        ),
        "precio_compra_minimo": min(precios_compra_validos) if precios_compra_validos else None,
        "precio_compra_maximo": max(precios_compra_validos) if precios_compra_validos else None,
    }

    productos_regalo = (
        list(filas_acumuladas.attrs["productos_regalo_sin_precio"])
        if isinstance(filas_acumuladas.attrs.get("productos_regalo_sin_precio"), list)
        else []
    )
    if not productos_regalo:
        for _, fila in filas_acumuladas.iterrows():
            clave_art = _limpiar_texto(fila.get("Clave Artículo"))
            p_compra = _limpiar_numero(fila.get("PRECIO COMPRA"))
            if clave_art and p_compra is not None and 0.0 <= p_compra <= 0.01:
                productos_regalo.append(
                    {
                        "clave_articulo": clave_art,
                        "descripcion": _limpiar_texto(fila.get("DESCRIPCION"))
                        or _limpiar_texto(fila.get("Descripción CFDI"))
                        or "",
                        "precio_compra": p_compra,
                        "proveedor": _limpiar_texto(fila.get("PROVEEDOR")) or "",
                    }
                )

    resumen: dict[str, Any] = {
        "tipo": "entradas_almacen",
        "generado_en": datetime.now(timezone.utc).isoformat(),
        "productos_nuevos": len(filas_nuevas),
        "productos_acumulados": len(filas_acumuladas),
        "duplicados_ignorados": duplicados_ignorados,
        "proveedores": proveedores,
        "total_proveedores": len(proveedores),
        "lineas": lineas,
        "total_lineas": len(lineas),
        "periodo": {
            "desde": fechas.min().strftime("%Y-%m-%d") if not fechas.empty else None,
            "hasta": fechas.max().strftime("%Y-%m-%d") if not fechas.empty else None,
        },
        "estadisticas_precios": estadisticas_precios,
        "trazabilidad_catalogo_sae": {
            "origen_clave": conteo_origen_clave,
            "origen_linea": conteo_origen_linea,
            "origen_proveedor": conteo_origen_proveedor,
        },
        "conversiones_a_metros": conversiones_a_metros,
        "productos_sin_linea": productos_sin_linea,
        "explicaciones_productos": [
            explicar_producto(clave, info)
            for clave, info in meta_por_clave.items()
            if info.get("fuentes") and (info.get("origen_linea") == "SIN_LINEA" or
                info["fuentes"].get("apoyo", {}).get("clave") not in (None, "", clave))
        ],
        "desglose_por_proveedor": desglose_proveedores,
        "desglose_por_linea": desglose_lineas,
        "productos_detalle": productos_detalle,
        "mostrando_productos_detalle": len(productos_detalle),
        "productos_regalo_sin_precio": productos_regalo,
        "archivo_excel": nombre_excel,
        "archivo_json": nombre_json,
    }
    if productos_regalo:
        from app.services.almacen.excel import construir_advertencia_productos_regalo

        adv_regalo = construir_advertencia_productos_regalo(productos_regalo)
        if adv_regalo:
            resumen["advertencia_productos_regalo"] = adv_regalo

    if datos_sincronizacion:
        resumen.update(datos_sincronizacion)

    return resumen


def _parsear_fecha_reporte(texto_fecha: str | None) -> date | None:
    if not texto_fecha:
        return None
    limpio = str(texto_fecha).strip()
    for fmt in ("%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(limpio, fmt).date()
        except ValueError:
            continue
    return None


def _a_decimal_seguro(valor: Any) -> Decimal:
    if valor is None:
        return Decimal("0.000000")
    try:
        return Decimal(str(valor)).quantize(Decimal("0.000001"))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0.000000")


def registrar_reporte_en_bd(
    resumen: dict[str, Any],
    *,
    usuario_id: int | None = None,
) -> int | None:
    """Guarda el resumen de un reporte y su desglose de artículos en la base de datos."""
    try:
        from app.core.database import Base, SessionLocal, engine
        from app.models.almacen import DetalleEntradaAlmacen, ReporteAlmacen

        Base.metadata.create_all(bind=engine)
        periodo = resumen.get("periodo") if isinstance(resumen.get("periodo"), dict) else {}
        fecha_carpeta = (
            str(resumen.get("fecha_carpeta") or periodo.get("hasta") or periodo.get("desde") or "SIN_FECHA")
            .strip()[:32]
        )
        fecha_date = (
            _parsear_fecha_reporte(resumen.get("fecha_carpeta"))
            or _parsear_fecha_reporte(periodo.get("hasta"))
            or _parsear_fecha_reporte(periodo.get("desde"))
        )
        productos = (
            resumen.get("productos_detalle")
            if isinstance(resumen.get("productos_detalle"), list)
            else []
        )

        with SessionLocal() as db:
            reporte = ReporteAlmacen(
                fecha_carpeta=fecha_carpeta,
                fecha_reporte=fecha_date,
                usuario_id=usuario_id,
                total_articulos=int(resumen.get("productos_acumulados") or len(productos)),
                resumen_json=json.dumps(resumen, ensure_ascii=False),
            )
            db.add(reporte)
            db.flush()

            for item in productos:
                if not isinstance(item, dict):
                    continue
                precios_venta = item.get("precios_venta") if isinstance(item.get("precios_venta"), dict) else {}
                db.add(
                    DetalleEntradaAlmacen(
                        reporte_id=reporte.id,
                        clave_articulo=str(item.get("clave_articulo") or "")[:64],
                        codigo_xml_original=str(item.get("codigo_xml_original") or "")[:128],
                        descripcion=str(item.get("descripcion") or "")[:500],
                        linea=str(item.get("linea") or "")[:64],
                        clave_proveedor=str(item.get("proveedor") or "")[:64],
                        unidad_procesada=str(item.get("unidad") or "")[:32],
                        cantidad=_a_decimal_seguro(item.get("cantidad")),
                        precio_compra=_a_decimal_seguro(item.get("precio_compra")),
                        factor_aplicado=str(item.get("factor") or "")[:64],
                        precios_venta_json=json.dumps(precios_venta, ensure_ascii=False),
                        origen_clave=str(item.get("origen_clave") or "")[:64],
                        origen_linea=str(item.get("origen_linea") or "")[:64],
                        origen_proveedor=str(item.get("origen_proveedor") or "")[:64],
                    )
                )
            db.commit()
            return reporte.id
    except Exception:
        return None


def guardar_resumen_json(resumen: dict, ruta: str | Path) -> Path:
    """Guarda resumen legible en disco y registra la corrida en la base de datos."""
    destino = Path(ruta)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(
        json.dumps(resumen, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    registrar_reporte_en_bd(resumen)
    return destino


__all__ = ["construir_resumen", "guardar_resumen_json", "registrar_reporte_en_bd"]
