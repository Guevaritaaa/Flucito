from app.services.almacen.fuentes.estado_drive import carpetas_con_novedades, marcar_procesadas
from app.services.almacen.fuentes.google_drive import CarpetaFactura, DriveArchivo


def test_estado_detecta_solo_documentos_nuevos() -> None:
    carpeta = CarpetaFactura(
        id="folder-1",
        nombre="04-08-2026",
        archivos=(
            DriveArchivo("xml-1", "factura.xml", "text/xml", "v1", "folder-1"),
            DriveArchivo("pdf-1", "factura.pdf", "application/pdf", "v1", "folder-1"),
        ),
    )
    estado = {"archivos": {"xml-1": "v1", "pdf-1": "v1"}}

    assert carpetas_con_novedades([carpeta], estado) == []

    carpeta_nueva = CarpetaFactura(
        id="folder-1",
        nombre="04-08-2026",
        archivos=carpeta.archivos + (
            DriveArchivo("txt-1", "factura.txt", "text/plain", "v1", "folder-1"),
        ),
    )
    assert carpetas_con_novedades([carpeta_nueva], estado) == [carpeta_nueva]

    marcar_procesadas([carpeta_nueva], estado)
    assert estado["archivos"]["txt-1"] == "v1"
