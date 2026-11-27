"""Consultas acotadas para el chat dedicado a Aspel SAE."""

from datetime import date
import json
from typing import Literal

from firebird.driver import DatabaseError
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from pydantic import BaseModel, ConfigDict, Field

from app.schemas.sae import EstadoInventarioSae, ResumenInventarioSae
from app.services.sae.compras import consultar_resumen_compras
from app.services.sae.conexion import SaeNoDisponible
from app.services.sae.conversaciones import verificar_permiso_chat_sae
from app.services.sae.facturacion import consultar_facturacion
from app.services.sae.inventario import consultar_inventario
from app.services.sae.periodos import PeriodoFueraDeCobertura

MetricaSae = Literal[
    "documentos", "importe", "facturas", "importe_facturado", "devoluciones", "importe_devoluciones",
    "articulos", "sin_existencia", "bajo_minimo", "existencias",
]
AgrupacionSae = Literal["total", "mes", "proveedor", "almacen"]
_METRICAS_FACTURACION = {"facturas", "importe_facturado", "devoluciones", "importe_devoluciones"}
_METRICAS_INVENTARIO = {"articulos", "sin_existencia", "bajo_minimo", "existencias"}


class ConsultaSaeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metrica: MetricaSae = Field(description="Compras: documentos o importe. Facturación: facturas y devoluciones, en conteo o importe. Inventario: artículos, alertas o existencias.")
    agrupacion: AgrupacionSae = "total"
    desde: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$", description="Fecha inicial inclusiva en YYYY-MM-DD.")
    hasta: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$", description="Fecha final inclusiva en YYYY-MM-DD.")
    moneda: str | None = Field(default=None, pattern="^[A-Z]{3}$", description="Código de moneda, por ejemplo MXN o USD.")
    proveedor: str | None = Field(default=None, min_length=2, max_length=100, description="Clave exacta o fragmento literal del nombre del proveedor.")
    almacen: str | None = Field(default=None, max_length=100, description="Solo inventario. Clave o nombre exacto del almacén activo.")
    articulo: str | None = Field(default=None, max_length=100, description="Solo inventario. Clave o fragmento literal del nombre del artículo.")
    estado_inventario: EstadoInventarioSae = "todos"


def _datos_inventario(inventario: ResumenInventarioSae, detalle: bool) -> dict:
    datos = inventario.model_dump(mode="json")
    campos = ["almacen", "articulos", "sin_existencia", "bajo_minimo"]
    if detalle:
        campos += ["total_resultados", "existencias"]
    return {campo: datos[campo] for campo in campos}


def _consulta_sae(consulta: ConsultaSaeInput) -> dict:
    metrica = consulta.metrica
    agrupacion = consulta.agrupacion
    if metrica in _METRICAS_INVENTARIO:
        if consulta.desde or consulta.hasta:
            raise ValueError("El inventario refleja las existencias del respaldo cargado y solo admite consultas al corte.")
        if consulta.moneda or consulta.proveedor or agrupacion not in {"total", "almacen"}:
            raise ValueError("El inventario admite filtros por almacén y artículo, y agrupación por almacén.")
        detalle = metrica == "existencias"
        inventario = consultar_inventario(
            almacen=consulta.almacen, articulo=consulta.articulo, estado=consulta.estado_inventario, por_pagina=8,
        )
        resultado = _datos_inventario(inventario, detalle)
        if agrupacion == "almacen" and consulta.almacen is None:
            resultado["por_almacen"] = [
                _datos_inventario(consultar_inventario(
                    almacen=almacen.clave, articulo=consulta.articulo, estado=consulta.estado_inventario, por_pagina=8,
                ), detalle)
                for almacen in inventario.almacenes
            ]
        fecha = inventario.corte.ultimo_movimiento
        fuente = f"Inventario al corte. Último movimiento registrado el {fecha.isoformat()}." if fecha else "Inventario al corte del respaldo."
        return {"fuente": fuente, "metrica": metrica, "agrupacion": agrupacion,
                "filtros": {"almacen": consulta.almacen, "articulo": consulta.articulo, "estado": consulta.estado_inventario}, **resultado}

    if consulta.almacen or consulta.articulo or consulta.estado_inventario != "todos":
        raise ValueError("Los filtros por almacén, artículo o estado de inventario se aplican a existencias.")
    desde = date.fromisoformat(consulta.desde) if consulta.desde else None
    hasta = date.fromisoformat(consulta.hasta) if consulta.hasta else None
    if metrica in _METRICAS_FACTURACION:
        if consulta.proveedor or agrupacion not in {"total", "mes"}:
            raise ValueError("La facturación admite periodo, moneda y agrupación total o mensual.")
        datos = consultar_facturacion(desde, hasta, moneda=consulta.moneda).model_dump(mode="json")
        campo = "tendencia_mensual" if agrupacion == "mes" else "totales_por_moneda"
        return {
            "fuente": f"Facturas registradas hasta el {datos['corte']['cobertura']['hasta']}.",
            "metrica": metrica, "agrupacion": agrupacion, "periodo": datos["periodo"],
            "moneda": consulta.moneda, "facturas": datos["facturas"], "devoluciones": datos["devoluciones"], campo: datos[campo],
        }

    if agrupacion == "almacen":
        raise ValueError("En compras usa agrupación total, mensual o por proveedor.")
    datos = consultar_resumen_compras(
        desde, hasta, moneda=consulta.moneda, proveedor=consulta.proveedor.strip() if consulta.proveedor else None,
        orden_proveedores="documentos" if metrica == "documentos" else "importe",
    ).model_dump(mode="json")
    campo = {"total": "totales_por_moneda", "mes": "tendencia_mensual", "proveedor": "principales_proveedores"}[agrupacion]
    return {
        "fuente": f"Compras registradas hasta el {datos['corte']['cobertura']['hasta']}.",
        "metrica": metrica, "agrupacion": agrupacion, "periodo": datos["periodo"],
        "documentos": datos["documentos"], campo: datos[campo], "filtros": {"moneda": consulta.moneda, "proveedor": consulta.proveedor},
    }


@tool(args_schema=ConsultaSaeInput)
def consultar_aspel_sae(
    config: RunnableConfig,
    metrica: MetricaSae,
    agrupacion: AgrupacionSae = "total",
    desde: str | None = None,
    hasta: str | None = None,
    moneda: str | None = None,
    proveedor: str | None = None,
    almacen: str | None = None,
    articulo: str | None = None,
    estado_inventario: EstadoInventarioSae = "todos",
) -> str:
    """Consulta compras, facturación o inventario al corte en el respaldo SAE de Empresa 02."""
    contexto = config.get("configurable", {})
    verificar_permiso_chat_sae(contexto.get("sae_session_id", ""), contexto.get("sae_usuario_id"))

    try:
        datos = _consulta_sae(ConsultaSaeInput(
            metrica=metrica, agrupacion=agrupacion, desde=desde, hasta=hasta, moneda=moneda, proveedor=proveedor,
            almacen=almacen, articulo=articulo, estado_inventario=estado_inventario,
        ))
    except PeriodoFueraDeCobertura as exc:
        return json.dumps({"ok": False, "error": str(exc), "cobertura": exc.cobertura.model_dump(mode="json")}, ensure_ascii=False)
    except ValueError as exc:
        return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)
    except (SaeNoDisponible, DatabaseError):
        return '{"ok": false, "error": "El respaldo de Aspel SAE no está disponible en este momento."}'

    return json.dumps({"ok": True, "empresa": "02", **datos}, ensure_ascii=False)
