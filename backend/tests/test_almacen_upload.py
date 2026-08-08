from pathlib import Path

from app.services.almacen.fuentes.subidor import agrupar_documentos


def test_agrupar_documentos_tolera_padding_de_folio(tmp_path: Path) -> None:
    xml = tmp_path / "INV-FAC2026001827-MX.xml"
    pdf = tmp_path / "FAC20261827.PDF"
    txt = tmp_path / "FAC20261827.TXT"

    grupos = agrupar_documentos([xml, pdf, txt])

    assert len(grupos) == 1
    assert grupos[0].xml == xml
    assert grupos[0].apoyo == (pdf, txt)
