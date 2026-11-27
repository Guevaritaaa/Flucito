import json
from datetime import date
from decimal import Decimal

from app.agents.tools import sae_tools
from app.schemas.sae import (
    AlmacenSae, CorteFacturacionSae, CorteInventarioSae, FacturacionMoneda, PeriodoSae,
    ResumenFacturacionSae, ResumenInventarioSae,
)


def test_herramienta_mantiene_facturas_y_devoluciones_separadas(monkeypatch):
    periodo = PeriodoSae(desde=date(2026, 4, 1), hasta=date(2026, 4, 30))
    total = FacturacionMoneda(moneda="USD", facturas=2, importe_facturado=Decimal("225.00"),
                              devoluciones=1, importe_devoluciones=Decimal("12.00"))
    autorizaciones = []
    monkeypatch.setattr(sae_tools, "verificar_permiso_chat_sae", lambda *args: autorizaciones.append(args))

    def facturas(desde, hasta, *, moneda):
        assert (desde, hasta, moneda) == (periodo.desde, periodo.hasta, "USD")
        return ResumenFacturacionSae(
            corte=CorteFacturacionSae(corte_id="prueba", cobertura=periodo), periodo=periodo, facturas=2,
            devoluciones=1, totales_por_moneda=[total], tendencia_mensual=[],
        )

    monkeypatch.setattr(sae_tools, "consultar_facturacion", facturas)
    resultado = json.loads(sae_tools.consultar_aspel_sae.invoke({
        "metrica": "importe_facturado", "moneda": "USD", "desde": "2026-04-01", "hasta": "2026-04-30",
    }, config={"configurable": {"sae_session_id": "sae-prueba", "sae_usuario_id": 7}}))

    assert autorizaciones == [("sae-prueba", 7)]
    assert resultado["ok"] is True
    assert resultado["totales_por_moneda"][0]["importe_facturado"] == "225.00"
    assert resultado["totales_por_moneda"][0]["importe_devoluciones"] == "12.00"


def test_herramienta_distingue_inventario_global_y_almacenes_y_rechaza_fechas(monkeypatch):
    almacenes = [AlmacenSae(clave=1, nombre="Principal"), AlmacenSae(clave=2, nombre="Secundario")]
    consultas = []
    monkeypatch.setattr(sae_tools, "verificar_permiso_chat_sae", lambda *_: None)

    def inventario(*, almacen, articulo, estado, por_pagina):
        consultas.append((almacen, articulo, estado, por_pagina))
        elegido = next((a for a in almacenes if a.clave == almacen), None)
        return ResumenInventarioSae(
            corte=CorteInventarioSae(corte_id="prueba", ultimo_movimiento=date(2026, 7, 1)),
            almacenes=almacenes, almacen=elegido, articulos=3, sin_existencia=1, bajo_minimo=2,
            total_resultados=3, pagina=1, por_pagina=por_pagina, existencias=[],
        )

    monkeypatch.setattr(sae_tools, "consultar_inventario", inventario)
    resultado = json.loads(sae_tools.consultar_aspel_sae.invoke({"metrica": "sin_existencia", "agrupacion": "almacen"}))
    assert resultado["almacen"] is None
    assert [a["almacen"]["clave"] for a in resultado["por_almacen"]] == [1, 2]
    assert "Último movimiento registrado el 2026-07-01" in resultado["fuente"]
    assert "existencias" not in resultado
    assert len(consultas) == 3

    historico = json.loads(sae_tools.consultar_aspel_sae.invoke({"metrica": "existencias", "desde": "2026-06-01"}))
    assert historico["ok"] is False
    assert "solo admite consultas al corte" in historico["error"]
    assert len(consultas) == 3
