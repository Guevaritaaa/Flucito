"""Consulta acotada de compras para el chat dedicado a Aspel SAE."""

from datetime import date
import json
from typing import Literal

from firebird.driver import DatabaseError
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from pydantic import BaseModel, ConfigDict, Field

from app.services.sae.compras import PeriodoFueraDeCobertura, consultar_resumen_compras
from app.services.sae.conexion import SaeNoDisponible
from app.services.sae.conversaciones import verificar_permiso_chat_sae


class ConsultaSaeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metrica: Literal["documentos", "importe"] = Field(description="Conteo de compras o total con impuestos.")
    agrupacion: Literal["total", "mes", "proveedor"] = "total"
    desde: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$", description="Fecha inicial inclusiva en YYYY-MM-DD.")
    hasta: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$", description="Fecha final inclusiva en YYYY-MM-DD.")
    moneda: str | None = Field(default=None, pattern="^[A-Z]{3}$", description="Código de moneda, por ejemplo MXN o USD.")
    proveedor: str | None = Field(default=None, min_length=2, max_length=100, description="Clave exacta o fragmento literal del nombre del proveedor.")


@tool(args_schema=ConsultaSaeInput)
def consultar_aspel_sae(
    config: RunnableConfig,
    metrica: Literal["documentos", "importe"],
    agrupacion: Literal["total", "mes", "proveedor"] = "total",
    desde: str | None = None,
    hasta: str | None = None,
    moneda: str | None = None,
    proveedor: str | None = None,
) -> str:
    """Consulta compras vigentes del respaldo SAE de Empresa 02. Para proveedor devuelve los cinco primeros por moneda según la métrica elegida."""
    contexto = config.get("configurable", {})
    verificar_permiso_chat_sae(contexto.get("sae_session_id", ""), contexto.get("sae_usuario_id"))

    try:
        resumen = consultar_resumen_compras(
            date.fromisoformat(desde) if desde else None,
            date.fromisoformat(hasta) if hasta else None,
            moneda=moneda,
            proveedor=proveedor.strip() if proveedor else None,
            orden_proveedores=metrica,
        )
    except PeriodoFueraDeCobertura as exc:
        return json.dumps({"ok": False, "error": str(exc), "cobertura": exc.cobertura.model_dump(mode="json")}, ensure_ascii=False)
    except ValueError as exc:
        return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)
    except (SaeNoDisponible, DatabaseError):
        return '{"ok": false, "error": "El respaldo de Aspel SAE no está disponible en este momento."}'

    datos = resumen.model_dump(mode="json")
    campos = {
        "total": "totales_por_moneda",
        "mes": "tendencia_mensual",
        "proveedor": "principales_proveedores",
    }
    return json.dumps({
        "ok": True,
        "empresa": datos["corte"]["empresa"],
        "compras_registradas_hasta": datos["corte"]["cobertura"]["hasta"],
        "periodo": datos["periodo"],
        "metrica": metrica,
        "agrupacion": agrupacion,
        "documentos": datos["documentos"],
        campos[agrupacion]: datos[campos[agrupacion]],
        "filtros": {"moneda": moneda, "proveedor": proveedor},
    }, ensure_ascii=False)
