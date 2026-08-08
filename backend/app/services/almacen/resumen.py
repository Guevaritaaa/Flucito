"""ConstrucciÃ³n de resumen conversacional para entradas de almacÃ©n."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


def construir_resumen(
    filas_nuevas: pd.DataFrame,
    filas_acumuladas: pd.DataFrame,
    duplicados_ignorados: int,
    nombre_excel: str,
    nombre_json: str,
) -> dict:
    """Crea datos compactos para que el asistente explique el Excel."""
    proveedores = sorted({
        str(valor).strip()
        for valor in filas_acumuladas.get("PROVEEDOR", [])
        if pd.notna(valor) and str(valor).strip()
    })

    fechas = pd.to_datetime(
        filas_acumuladas.get("Fecha de Ãºltima compra", pd.Series(dtype=str)),
        dayfirst=True,
        errors="coerce",
    ).dropna()

    resumen = {
        "tipo": "entradas_almacen",
        "generado_en": datetime.now(timezone.utc).isoformat(),
        "productos_nuevos": len(filas_nuevas),
        "productos_acumulados": len(filas_acumuladas),
        "duplicados_ignorados": duplicados_ignorados,
        "proveedores": proveedores,
        "total_proveedores": len(proveedores),
        "periodo": {
            "desde": fechas.min().strftime("%Y-%m-%d") if not fechas.empty else None,
            "hasta": fechas.max().strftime("%Y-%m-%d") if not fechas.empty else None,
        },
        "archivo_excel": nombre_excel,
        "archivo_json": nombre_json,
    }
    return resumen


def guardar_resumen_json(resumen: dict, ruta: str | Path) -> Path:
    """Guarda resumen legible y estable para consumo posterior del asistente."""
    destino = Path(ruta)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(
        json.dumps(resumen, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return destino


__all__ = ["construir_resumen", "guardar_resumen_json"]
