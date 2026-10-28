"""Esquemas Pydantic planos para las herramientas del agente Flucito."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ConsultarDriveInput(BaseModel):
    """Parámetros de entrada para consultar o auditar Google Drive (solo lectura)."""

    modo_consulta: Literal[
        "explorar_estructura",
        "auditar_facturas",
        "buscar_reportes_excel",
        "inspeccionar_xml",
    ] = Field(
        description=(
            "Modo de lectura: 'explorar_estructura' lista carpetas y archivos; "
            "'auditar_facturas' detecta carpetas vacías, sin XML, XML sin PDF/TXT o sin reporte Excel; "
            "'buscar_reportes_excel' busca reportes Excel históricos para descarga; "
            "'inspeccionar_xml' lee en solo lectura de qué trata un archivo XML o factura en Drive."
        )
    )
    ubicacion: Literal[
        "todas",
        "entradas_al_inventario",
        "documentos_entrada",
        "raiz",
    ] = Field(
        default="todas",
        description="Sección del Drive donde realizar la consulta.",
    )
    carpeta_o_fecha: str | None = Field(
        default=None,
        description="Fecha (DD-MM-AAAA o AAAA-MM-DD) o nombre/ruta de carpeta específica a consultar.",
    )
    filtro_auditoria: Literal[
        "todos",
        "incompletas",
        "sin_xml",
        "sin_apoyo",
        "sin_reporte_excel",
        "completas",
    ] = Field(
        default="todos",
        description="Filtro para modo 'auditar_facturas' según el tipo de hallazgo buscado.",
    )
    proveedor: str | None = Field(
        default=None,
        description="Filtro opcional por nombre de proveedor al buscar reportes Excel históricos.",
    )
    incluir_archivos: bool = Field(
        default=True,
        description="Si es True, incluye la lista de nombres de archivos dentro de cada carpeta.",
    )


class GestionarArchivosDriveInput(BaseModel):
    """Parámetros de entrada para organizar, crear, mover o eliminar carpetas y archivos en Google Drive."""

    accion: Literal[
        "organizar_todo",
        "archivar_carpetas_procesadas",
        "reubicar_mal_ubicadas",
        "mover_elemento",
        "crear_carpeta",
        "eliminar_elemento",
    ] = Field(
        description=(
            "Acción a ejecutar: 'organizar_todo' ordena todo el Drive automáticamente; "
            "'archivar_carpetas_procesadas' mueve carpetas ya con Excel a DOCUMENTOS ENTRADA; "
            "'reubicar_mal_ubicadas' regresa carpetas sin Excel a ENTRADAS AL INVENTARIO; "
            "'mover_elemento' mueve una carpeta/archivo de ruta_origen a ruta_destino; "
            "'crear_carpeta' crea ruta_destino; "
            "'eliminar_elemento' envía ruta_origen a la papelera."
        )
    )
    ruta_origen: str | None = Field(
        default=None,
        description=(
            "Nombre o ruta del archivo/carpeta origen para 'mover_elemento' o 'eliminar_elemento' "
            "(ej. '18-03-2026' o 'ENTRADAS AL INVENTARIO/18-03-2026/factura.xml')."
        ),
    )
    ruta_destino: str | None = Field(
        default=None,
        description=(
            "Carpeta destino para 'mover_elemento' (ej. 'DOCUMENTOS ENTRADA') "
            "o ruta de la nueva carpeta para 'crear_carpeta' (ej. 'ENTRADAS AL INVENTARIO/25-03-2026')."
        ),
    )
    confirmar_eliminar_con_contenido: bool = Field(
        default=False,
        description=(
            "En 'eliminar_elemento': usar False primero; cambiar a True únicamente cuando el "
            "usuario haya confirmado explícitamente eliminar una carpeta que contiene archivos."
        ),
    )


class ConsultarAlmacenInput(BaseModel):
    """Parámetros de entrada para consultar datos locales del almacén y catálogo de factores."""

    tipo_consulta: Literal[
        "resumen_general",
        "buscar_entradas",
        "catalogo_factores",
    ] = Field(
        default="resumen_general",
        description=(
            "'resumen_general' devuelve totales, proveedores y últimas entradas procesadas; "
            "'buscar_entradas' filtra renglones de la base acumulada local; "
            "'catalogo_factores' muestra factores de utilidad 1..8, líneas asociadas y personalizados."
        ),
    )
    proveedor: str | None = Field(
        default=None,
        description="Filtro parcial por nombre o código de proveedor.",
    )
    linea: str | None = Field(
        default=None,
        description="Filtro por código de línea (ej. 'FESTO', 'PARKER').",
    )
    producto_o_clave: str | None = Field(
        default=None,
        description="Filtro por clave de artículo o texto en la descripción del producto.",
    )
    folio_factura: str | None = Field(
        default=None,
        description="Filtro por número de folio de factura.",
    )
    fecha: str | None = Field(
        default=None,
        description="Filtro por fecha de entrada o documento.",
    )
    limite: int = Field(
        default=25,
        ge=1,
        le=100,
        description="Cantidad máxima de registros a devolver en 'buscar_entradas'.",
    )


class GenerarEntradasAlmacenInput(BaseModel):
    """Parámetros de entrada para sincronizar facturas y generar reportes de entradas de almacén."""

    confirmar_solo_xml: bool | None = Field(
        default=None,
        description="True ('y') si el usuario autoriza procesar carpetas con solo XML; False ('n') si cancela.",
    )
    factores_elegidos: dict[str, str] | None = Field(
        default=None,
        description="Mapa {CODIGO_LINEA: NUMERO_O_NOMBRE_FACTOR} indicado por el usuario.",
    )
    guardar_factores: bool | None = Field(
        default=None,
        description="True ('y') si el usuario autoriza guardar los factores elegidos para futuras compras.",
    )
    cambiar_xro_a_mtr: bool | None = Field(
        default=None,
        description="True ('y') o False ('n') para cambiar la unidad XRO a MTR en rollos o carretes.",
    )
    dividir_precio_entre_metros: bool | None = Field(
        default=None,
        description="True ('y') o False ('n') para dividir el precio de compra entre los metros del rollo.",
    )
    decisiones_rollos: dict[str, dict[str, object]] | None = Field(
        default=None,
        description="Decisiones específicas por clave de artículo {'CLAVE': {'cambiar_a_mtr': bool, 'dividir_entre_metros': bool}}.",
    )


class ActualizarPreciosReportesInput(BaseModel):
    """Parámetros de entrada para recalcular y actualizar precios/fórmulas en reportes Excel ya generados."""

    fecha: str | None = Field(
        default=None,
        description="Fecha opcional (DD-MM-AAAA) para actualizar solo los reportes de esa fecha; omitir para revisar todos.",
    )
    factores_elegidos: dict[str, str] | None = Field(
        default=None,
        description="Mapa opcional {CODIGO_LINEA: NUMERO_O_NOMBRE_FACTOR} para aplicar durante el recálculo.",
    )
