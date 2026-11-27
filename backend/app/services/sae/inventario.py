"""Existencias de productos activos y sus mínimos al corte del respaldo SAE."""

from app.schemas.sae import AlmacenSae, ArticuloInventarioSae, CorteInventarioSae, EstadoInventarioSae, ResumenInventarioSae
from app.services.sae.conexion import SaeNoDisponible, conectar_sae

_SIN_EXISTENCIA = "EXISTENCIA <= 0"
_BAJO_MINIMO = "MINIMO > 0 AND EXISTENCIA < MINIMO"
_CONDICIONES_ESTADO = {"sin_existencia": _SIN_EXISTENCIA, "bajo_minimo": _BAJO_MINIMO}


class FiltroInventarioInvalido(ValueError):
    """La consulta solicita un alcance de inventario no disponible."""


def consultar_inventario(
    *, almacen: int | str | None = None, articulo: str | None = None,
    estado: EstadoInventarioSae = "todos", pagina: int = 1, por_pagina: int = 20,
) -> ResumenInventarioSae:
    if pagina < 1 or not 1 <= por_pagina <= 50:
        raise FiltroInventarioInvalido("La página debe empezar en 1 y admite hasta 50 artículos.")
    with conectar_sae() as conexion:
        cursor = conexion.cursor()
        origen = cursor.execute("SELECT HUELLA, ULTIMO_MOVIMIENTO FROM FLUCITO_SAE_CORTE_INVENTARIO").fetchone()
        if origen is None:
            raise SaeNoDisponible("El respaldo carece de metadatos de inventario")
        huella, ultimo_movimiento = origen
        cursor.execute("SELECT CLAVE, NOMBRE FROM FLUCITO_SAE_ALMACENES ORDER BY CLAVE")
        almacenes = [AlmacenSae(clave=clave, nombre=nombre or f"Almacén {clave}") for clave, nombre in cursor]
        almacen_elegido = None
        filtro = "ALMACEN IS NULL"
        parametros: list[int | str] = []
        if almacen is not None:
            clave_o_nombre = str(almacen).strip()
            if clave_o_nombre.isdecimal():
                coincidencias = [a for a in almacenes if a.clave == int(clave_o_nombre)]
            else:
                coincidencias = [a for a in almacenes if a.nombre.casefold() == clave_o_nombre.casefold()]
            if len(coincidencias) != 1:
                opciones = ", ".join(f"{a.clave} ({a.nombre})" for a in almacenes)
                raise FiltroInventarioInvalido(f"Usa una clave o nombre de almacén activo. Disponibles: {opciones}.")
            almacen_elegido = coincidencias[0]
            filtro = "ALMACEN = ?"
            parametros.append(almacen_elegido.clave)
        if articulo and articulo.strip():
            filtro += " AND (CLAVE CONTAINING CAST(? AS VARCHAR(100)) OR NOMBRE CONTAINING CAST(? AS VARCHAR(100)))"
            parametros.extend((articulo.strip(), articulo.strip()))

        articulos, sin_existencia, bajo_minimo = cursor.execute(f"""
            SELECT COUNT(*), COUNT(CASE WHEN {_SIN_EXISTENCIA} THEN 1 END),
                   COUNT(CASE WHEN {_BAJO_MINIMO} THEN 1 END)
            FROM FLUCITO_SAE_INVENTARIO WHERE {filtro}
        """, parametros).fetchone()
        total_resultados = articulos
        if estado != "todos":
            filtro += f" AND ({_CONDICIONES_ESTADO[estado]})"
            total_resultados = sin_existencia if estado == "sin_existencia" else bajo_minimo

        desde = (pagina - 1) * por_pagina + 1
        existencias = []
        if desde <= total_resultados:
            cursor.execute(f"""
                SELECT CLAVE, NOMBRE, UNIDAD, EXISTENCIA, MINIMO
                FROM FLUCITO_SAE_INVENTARIO WHERE {filtro}
                ORDER BY CLAVE ROWS ? TO ?
            """, [*parametros, desde, desde + por_pagina - 1])
            existencias = [
                ArticuloInventarioSae(clave=clave, nombre=nombre, unidad=unidad, existencia=existencia, minimo=minimo)
                for clave, nombre, unidad, existencia, minimo in cursor
            ]

    return ResumenInventarioSae(
        corte=CorteInventarioSae(corte_id=f"empresa02-{huella.strip()}", ultimo_movimiento=ultimo_movimiento),
        almacen=almacen_elegido, almacenes=almacenes, articulos=articulos, sin_existencia=sin_existencia,
        bajo_minimo=bajo_minimo, total_resultados=total_resultados, pagina=pagina, por_pagina=por_pagina,
        existencias=existencias,
    )
