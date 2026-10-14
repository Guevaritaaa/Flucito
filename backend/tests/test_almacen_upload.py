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


def test_agrupar_documentos_empareja_txt_4_digitos_y_no_descarta(tmp_path: Path) -> None:
    xml_1864 = tmp_path / "INV-INV202601864-MX-Invoice-4.0.xml"
    xml_1865 = tmp_path / "INV-INV202601865-MX-Invoice-4.0.xml"
    xml_1866 = tmp_path / "INV-INV202601866-MX-Invoice-4.0.xml"
    txt_1864 = tmp_path / "1864.txt"
    txt_1865 = tmp_path / "1865.txt"
    txt_1866 = tmp_path / "1866.txt"
    extra_txt = tmp_path / "9999.txt"

    grupos = agrupar_documentos(
        [xml_1864, xml_1865, xml_1866, txt_1864, txt_1865, txt_1866, extra_txt]
    )

    assert len(grupos) == 3
    assert grupos[0].xml == xml_1864
    assert grupos[0].apoyo == (txt_1864, extra_txt)
    assert grupos[1].xml == xml_1865
    assert grupos[1].apoyo == (txt_1865,)
    assert grupos[2].xml == xml_1866
    assert grupos[2].apoyo == (txt_1866,)

