from app.services.almacen.fuentes.google_drive import agrupar_por_carpeta


def test_agrupar_documentos_por_subcarpeta() -> None:
    carpetas = [
        {
            "id": "folder-1",
            "name": "04-08-2026",
            "mimeType": "application/vnd.google-apps.folder",
        },
    ]
    archivos = [
        {"id": "xml-1", "name": "factura.xml", "parents": ["folder-1"]},
        {"id": "pdf-1", "name": "factura.pdf", "parents": ["folder-1"]},
        {"id": "txt-1", "name": "factura.txt", "parents": ["folder-1"]},
        {"id": "img-1", "name": "vista.png", "parents": ["folder-1"]},
    ]

    resultado = agrupar_por_carpeta(carpetas, archivos)

    assert len(resultado) == 1
    assert resultado[0].nombre == "04-08-2026"
    assert [archivo.extension for archivo in resultado[0].archivos] == [".xml", ".pdf", ".txt"]
    assert len(resultado[0].xml) == 1
    assert len(resultado[0].apoyo) == 2
