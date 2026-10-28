"""Pruebas unitarias para el servicio de navegación, auditoría y gestión por rutas en Google Drive (Fase 1)."""

from __future__ import annotations

from app.core.config import settings
from app.services.almacen.fuentes import google_drive_client, navegador_drive
from app.services.almacen.fuentes.google_drive import MIME_CARPETA


def _estructura_drive_prueba() -> dict[str, list[dict[str, str]]]:
    """Construye un árbol simulado de Google Drive para pruebas de exploración, auditoría y gestión."""
    return {
        "root-id": [
            {"id": "entradas-id", "name": "ENTRADAS AL INVENTARIO", "mimeType": MIME_CARPETA},
            {"id": "historicos-id", "name": "DOCUMENTOS ENTRADA", "mimeType": MIME_CARPETA},
            {"id": "suelto-raiz-id", "name": "nota_raiz.txt", "mimeType": "text/plain"},
        ],
        "entradas-id": [
            {"id": "carpeta-completa", "name": "18-03-2026", "mimeType": MIME_CARPETA},
            {"id": "carpeta-incompleta", "name": "19-03-2026", "mimeType": MIME_CARPETA},
            {"id": "carpeta-sin-xml", "name": "20-03-2026", "mimeType": MIME_CARPETA},
            {"id": "carpeta-vacia", "name": "Carpeta Vacia", "mimeType": MIME_CARPETA},
        ],
        "carpeta-completa": [
            {"id": "xml-100", "name": "factura-100.xml", "mimeType": "text/xml"},
            {"id": "pdf-100", "name": "factura-100.pdf", "mimeType": "application/pdf"},
        ],
        "carpeta-incompleta": [
            {"id": "xml-201", "name": "2026000201.xml", "mimeType": "text/xml"},
            {"id": "pdf-201", "name": "2026000201.pdf", "mimeType": "application/pdf"},
            {"id": "xml-202-sin-apoyo", "name": "2026000202.xml", "mimeType": "text/xml"},
        ],
        "carpeta-sin-xml": [
            {"id": "pdf-huerfano", "name": "remision_300.pdf", "mimeType": "application/pdf"},
        ],
        "carpeta-vacia": [],
        "historicos-id": [
            {"id": "hist-15", "name": "15-03-2026", "mimeType": MIME_CARPETA},
            {"id": "hist-mal-ubicada", "name": "21-03-2026", "mimeType": MIME_CARPETA},
        ],
        "hist-15": [
            {
                "id": "rep-lote-15",
                "name": "ENTRADAS_ALMACEN_15-03-2026.xlsx",
                "mimeType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            },
            {"id": "prov-15", "name": "Aceros del Norte - 15-03-2026", "mimeType": MIME_CARPETA},
        ],
        "prov-15": [
            {"id": "xml-15", "name": "factura-500.xml", "mimeType": "text/xml"},
            {"id": "txt-15", "name": "factura-500.txt", "mimeType": "text/plain"},
            {
                "id": "rep-prov-15",
                "name": "ENTRADAS_ALMACEN_Aceros del Norte_15-03-2026.xlsx",
                "mimeType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            },
        ],
        "hist-mal-ubicada": [
            {"id": "xml-21", "name": "factura-600.xml", "mimeType": "text/xml"},
            {"id": "pdf-21", "name": "factura-600.pdf", "mimeType": "application/pdf"},
        ],
    }


def test_buscar_reportes_historicos_por_proveedor_y_sin_fecha(monkeypatch) -> None:
    """Verifica que buscar_reportes_historicos soporte búsqueda global o filtrada por proveedor."""
    estructura = _estructura_drive_prueba()
    monkeypatch.setattr(settings, "google_drive_folder_id", "root-id")
    monkeypatch.setattr(
        google_drive_client,
        "_listar_hijos",
        lambda cliente, carpeta_id: estructura.get(carpeta_id, []),
    )

    todos = google_drive_client.buscar_reportes_historicos(fecha=None, cliente=object())
    assert [r["id"] for r in todos] == ["rep-lote-15", "rep-prov-15"]

    por_proveedor = google_drive_client.buscar_reportes_historicos(
        fecha=None,
        cliente=object(),
        proveedor="Aceros del Norte",
    )
    assert [r["id"] for r in por_proveedor] == ["rep-prov-15"]
    assert por_proveedor[0]["fecha"] == "15-03-2026"


def test_explorar_estructura_drive_general_y_por_carpeta(monkeypatch) -> None:
    """Verifica la exploración completa del árbol de Drive y la consulta de una carpeta puntual."""
    estructura = _estructura_drive_prueba()
    monkeypatch.setattr(settings, "google_drive_folder_id", "root-id")
    monkeypatch.setattr(
        navegador_drive,
        "_listar_hijos",
        lambda cliente, carpeta_id: estructura.get(carpeta_id, []),
    )

    vista_general = navegador_drive.explorar_estructura_drive(
        ubicacion="todas",
        cliente=object(),
        carpeta_raiz_id="root-id",
    )
    assert vista_general["ok"] is True
    assert vista_general["resumen"]["total_carpetas_en_entradas_al_inventario"] == 4
    assert vista_general["resumen"]["total_carpetas_en_documentos_entrada"] == 2
    assert vista_general["contenedores"]["raiz"]["archivos_sueltos_en_raiz"] == ["nota_raiz.txt"]

    vista_carpeta = navegador_drive.explorar_estructura_drive(
        ubicacion="todas",
        carpeta_o_fecha="2026-03-18",
        cliente=object(),
        carpeta_raiz_id="root-id",
    )
    assert vista_carpeta["ok"] is True
    assert vista_carpeta["total_carpetas_encontradas"] == 1
    carpeta_18 = vista_carpeta["carpetas_encontradas"][0]
    assert carpeta_18["ruta"] == "ENTRADAS AL INVENTARIO/18-03-2026"
    assert carpeta_18["conteo_archivos"]["xml"] == 1
    assert carpeta_18["conteo_archivos"]["pdf"] == 1


def test_auditar_facturas_drive_detecta_sin_xml_sin_apoyo_y_mal_ubicadas(monkeypatch) -> None:
    """Verifica que la auditoría rápida híbrida detecte carpetas vacías, sin XML, sin apoyo y sin Excel."""
    estructura = _estructura_drive_prueba()
    monkeypatch.setattr(settings, "google_drive_folder_id", "root-id")
    monkeypatch.setattr(
        navegador_drive,
        "_listar_hijos",
        lambda cliente, carpeta_id: estructura.get(carpeta_id, []),
    )

    auditoria = navegador_drive.auditar_facturas_drive(
        ubicacion="todas",
        filtro_auditoria="todos",
        cliente=object(),
        carpeta_raiz_id="root-id",
    )
    assert auditoria["ok"] is True
    hallazgos = auditoria["resumen_hallazgos"]

    # Carpetas sin XML (la vacía y la que solo tiene un PDF huérfano)
    assert set(hallazgos["carpetas_sin_xml"]) == {
        "ENTRADAS AL INVENTARIO/20-03-2026",
        "ENTRADAS AL INVENTARIO/Carpeta Vacia",
    }
    assert hallazgos["carpetas_vacias"] == ["ENTRADAS AL INVENTARIO/Carpeta Vacia"]

    # Carpetas con XML sin apoyo o apoyos huérfanos
    rutas_incompletas = {item["ruta"]: item for item in hallazgos["carpetas_con_xml_sin_apoyo"]}
    assert "ENTRADAS AL INVENTARIO/19-03-2026" in rutas_incompletas
    assert rutas_incompletas["ENTRADAS AL INVENTARIO/19-03-2026"]["xml_sin_apoyo"] == [
        "2026000202.xml"
    ]
    assert "ENTRADAS AL INVENTARIO/20-03-2026" in rutas_incompletas
    assert rutas_incompletas["ENTRADAS AL INVENTARIO/20-03-2026"]["apoyos_huerfanos"] == [
        "remision_300.pdf"
    ]

    # Carpetas mal ubicadas en DOCUMENTOS ENTRADA
    assert hallazgos["carpetas_mal_ubicadas"] == ["DOCUMENTOS ENTRADA/21-03-2026"]

    # Carpetas completas (con XML y todos sus apoyos correspondientes)
    assert set(hallazgos["carpetas_completas"]) == {
        "ENTRADAS AL INVENTARIO/18-03-2026",
        "DOCUMENTOS ENTRADA/15-03-2026",
        "DOCUMENTOS ENTRADA/21-03-2026",
    }


def test_mover_crear_y_eliminar_con_confirmacion_de_seguridad(monkeypatch) -> None:
    """Verifica creación de carpetas, movimiento puntual y protección al eliminar carpetas con archivos."""
    estructura = _estructura_drive_prueba()
    monkeypatch.setattr(settings, "google_drive_folder_id", "root-id")
    monkeypatch.setattr(
        navegador_drive,
        "_listar_hijos",
        lambda cliente, carpeta_id: estructura.get(carpeta_id, []),
    )
    monkeypatch.setattr(
        navegador_drive,
        "buscar_carpeta_hija",
        lambda cliente, nombre, padre_id: next(
            (
                item["id"]
                for item in estructura.get(padre_id, [])
                if item.get("mimeType") == MIME_CARPETA and item.get("name") == nombre
            ),
            None,
        ),
    )

    carpetas_creadas: list[tuple[str, str]] = []
    movimientos: list[tuple[str, str, str | None]] = []
    eliminados: list[str] = []

    def _mock_crear(cliente, nombre: str, padre_id: str) -> str:
        nuevo_id = f"nuevo-{nombre}"
        carpetas_creadas.append((nombre, padre_id))
        estructura.setdefault(padre_id, []).append(
            {"id": nuevo_id, "name": nombre, "mimeType": MIME_CARPETA}
        )
        estructura[nuevo_id] = []
        return nuevo_id

    monkeypatch.setattr(navegador_drive, "buscar_o_crear_carpeta", _mock_crear)
    monkeypatch.setattr(
        navegador_drive,
        "mover_archivo",
        lambda cliente, archivo_id, destino_id, carpeta_origen_id=None: movimientos.append(
            (archivo_id, destino_id, carpeta_origen_id)
        ),
    )
    monkeypatch.setattr(
        navegador_drive,
        "eliminar_archivo",
        lambda cliente, archivo_id: eliminados.append(archivo_id),
    )

    # 1. Crear carpeta nueva por nombre corto (se ubica en ENTRADAS AL INVENTARIO)
    res_crear = navegador_drive.crear_carpeta_por_ruta(
        "25-03-2026",
        cliente=object(),
        carpeta_raiz_id="root-id",
    )
    assert res_crear["ok"] is True
    assert res_crear["creada"] is True
    assert res_crear["ruta_completa"] == "ENTRADAS AL INVENTARIO/25-03-2026"

    # 2. Mover carpeta mal ubicada de DOCUMENTOS ENTRADA hacia ENTRADAS AL INVENTARIO
    res_mover = navegador_drive.mover_elemento_por_ruta(
        ruta_origen="DOCUMENTOS ENTRADA/21-03-2026",
        ruta_destino="ENTRADAS AL INVENTARIO",
        cliente=object(),
        carpeta_raiz_id="root-id",
    )
    assert res_mover["ok"] is True
    assert res_mover["movido"] is True
    assert ("hist-mal-ubicada", "entradas-id", "historicos-id") in movimientos

    # 3. Eliminar carpeta vacía (se elimina directamente sin pedir confirmación)
    res_borrar_vacia = navegador_drive.eliminar_elemento_por_ruta(
        ruta_objetivo="Carpeta Vacia",
        confirmar_eliminar_con_contenido=False,
        cliente=object(),
        carpeta_raiz_id="root-id",
    )
    assert res_borrar_vacia["ok"] is True
    assert res_borrar_vacia["eliminado"] is True
    assert "carpeta-vacia" in eliminados

    # 4. Intentar eliminar carpeta con archivos sin confirmación -> se bloquea y pide confirmación
    res_bloqueado = navegador_drive.eliminar_elemento_por_ruta(
        ruta_objetivo="18-03-2026",
        confirmar_eliminar_con_contenido=False,
        cliente=object(),
        carpeta_raiz_id="root-id",
    )
    assert res_bloqueado["ok"] is False
    assert res_bloqueado["requiere_confirmacion"] is True
    assert res_bloqueado["archivos_encontrados"] == ["factura-100.pdf", "factura-100.xml"]
    assert "carpeta-completa" not in eliminados

    # 5. Eliminar carpeta con archivos confirmando explícitamente
    res_confirmado = navegador_drive.eliminar_elemento_por_ruta(
        ruta_objetivo="18-03-2026",
        confirmar_eliminar_con_contenido=True,
        cliente=object(),
        carpeta_raiz_id="root-id",
    )
    assert res_confirmado["ok"] is True
    assert res_confirmado["eliminado"] is True
    assert "carpeta-completa" in eliminados

    # 6. Proteger contenedores principales del sistema
    res_protegido = navegador_drive.eliminar_elemento_por_ruta(
        ruta_objetivo="ENTRADAS AL INVENTARIO",
        confirmar_eliminar_con_contenido=True,
        cliente=object(),
        carpeta_raiz_id="root-id",
    )
    assert res_protegido["ok"] is False
    assert "entradas-id" not in eliminados
