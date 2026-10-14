"""Script para restaurar el entorno de pruebas en Google Drive."""

import logging
from pathlib import Path
from app.core.config import settings
from app.services.almacen.fuentes.google_drive_client import (
    crear_cliente_drive,
    buscar_carpeta_hija,
    buscar_o_crear_carpeta,
    MIME_CARPETA,
    CARPETA_ENTRADAS_AL_INVENTARIO,
    CARPETA_REPORTES_HISTORICOS,
    eliminar_archivo,
    mover_archivo,
    _listar_hijos,
)
from app.services.almacen.excel import CARPETA_DATOS
from app.services.almacen.fuentes.estado_drive import NOMBRE_ESTADO

logger = logging.getLogger(__name__)

def restaurar_entorno_pruebas() -> dict:
    """Restaura los archivos a la carpeta de entrada y limpia generados."""
    logger.info("Iniciando restauración del entorno de pruebas...")
    try:
        cliente = crear_cliente_drive()
    except Exception as e:
        return {"ok": False, "error": f"Error conectando a Drive: {e}"}

    carpeta_raiz_id = settings.google_drive_folder_id
    if not carpeta_raiz_id:
        return {"ok": False, "error": "Falta GOOGLE_DRIVE_FOLDER_ID"}

    carpeta_entrada_id = buscar_o_crear_carpeta(
        cliente, CARPETA_ENTRADAS_AL_INVENTARIO, carpeta_raiz_id
    )
    carpeta_historico_id = buscar_carpeta_hija(
        cliente, CARPETA_REPORTES_HISTORICOS, carpeta_raiz_id
    )

    if not carpeta_historico_id:
        return {"ok": False, "error": "No hay carpeta de históricos para restaurar."}

    # 1. Limpiar estado local
    ruta_estado = Path(CARPETA_DATOS) / NOMBRE_ESTADO
    if ruta_estado.exists():
        ruta_estado.unlink()
    
    for ext in ("*.xlsx", "*.json", "*.txt"):
        for f in Path(CARPETA_DATOS).glob(ext):
            f.unlink()

    # 2. Recorrer DOCUMENTOS ENTRADA/{fecha}
    carpetas_fecha = [
        item for item in _listar_hijos(cliente, carpeta_historico_id)
        if item.get("mimeType") == MIME_CARPETA
    ]

    archivos_movidos = 0
    archivos_eliminados = 0
    advertencias = []

    for c_fecha in carpetas_fecha:
        fecha_nombre = c_fecha.get("name")
        c_fecha_id = c_fecha.get("id")

        entrada_fecha_id = buscar_carpeta_hija(cliente, fecha_nombre, carpeta_entrada_id)
        reutilizar_carpeta = entrada_fecha_id is None
        destino_archivos_id = c_fecha_id if reutilizar_carpeta else entrada_fecha_id

        elementos_fecha = _listar_hijos(cliente, c_fecha_id)

        for item in elementos_fecha:
            item_name = item.get("name", "")
            item_id = item.get("id")

            # Es un archivo directo en la carpeta de fecha (ej. reporte batch)
            if item.get("mimeType") != MIME_CARPETA:
                if item_name.startswith("ENTRADAS_ALMACEN_"):
                    try:
                        eliminar_archivo(cliente, item_id)
                        archivos_eliminados += 1
                    except Exception as e:
                        advertencias.append(f"No se pudo eliminar el reporte {item_name}: {e}")
                elif not reutilizar_carpeta:
                    try:
                        mover_archivo(cliente, item_id, destino_archivos_id)
                        archivos_movidos += 1
                    except Exception as e:
                        advertencias.append(f"No se pudo mover el archivo {item_name}: {e}")
                continue

            # Es una carpeta de proveedor
            c_prov_id = item_id
            c_prov_name = item_name
            archivos_prov = _listar_hijos(cliente, c_prov_id)

            for a_prov in archivos_prov:
                a_prov_name = a_prov.get("name", "")
                a_prov_id = a_prov.get("id")

                if a_prov_name.startswith("ENTRADAS_ALMACEN_"):
                    try:
                        eliminar_archivo(cliente, a_prov_id)
                        archivos_eliminados += 1
                    except Exception as e:
                        advertencias.append(f"No se pudo eliminar el reporte {a_prov_name}: {e}")
                else:
                    try:
                        mover_archivo(cliente, a_prov_id, destino_archivos_id)
                        archivos_movidos += 1
                    except Exception as e:
                        advertencias.append(f"No se pudo mover el archivo {a_prov_name}: {e}")

            # Eliminar la carpeta del proveedor
            try:
                eliminar_archivo(cliente, c_prov_id)
            except Exception as e:
                advertencias.append(f"No se pudo eliminar la carpeta del proveedor '{c_prov_name}': {e}")

        if reutilizar_carpeta:
            try:
                mover_archivo(cliente, c_fecha_id, carpeta_entrada_id)
            except Exception as e:
                advertencias.append(f"No se pudo mover la carpeta de fecha '{fecha_nombre}' a entradas: {e}")
        else:
            try:
                eliminar_archivo(cliente, c_fecha_id)
            except Exception:
                try:
                    for item_ent in _listar_hijos(cliente, entrada_fecha_id):
                        mover_archivo(cliente, item_ent["id"], c_fecha_id)
                    eliminar_archivo(cliente, entrada_fecha_id)
                    mover_archivo(cliente, c_fecha_id, carpeta_entrada_id)
                except Exception as e:
                    advertencias.append(f"No se pudo eliminar la carpeta de fecha '{fecha_nombre}': {e}")

    return {
        "ok": True,
        "movidos": archivos_movidos,
        "eliminados": archivos_eliminados,
        "advertencias": advertencias
    }
