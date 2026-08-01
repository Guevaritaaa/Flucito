import json
from pathlib import Path

from app.agents.tools import generar_reporte_cfdi_job
from app.services.cfdi import jobs


BASE_DIR = Path(__file__).parent
XML_VALIDO = BASE_DIR / "fixtures" / "cfdi_valido.xml"


def test_generar_reporte_cfdi_job_usa_rutas_del_job(tmp_path: Path) -> None:
    directorio_job = tmp_path / "job"
    directorio_job.mkdir()
    xml = directorio_job / "factura.xml"
    xml.write_bytes(XML_VALIDO.read_bytes())

    jobs.CFDI_JOBS.clear()
    job_id = jobs.crear_job(directorio_job, [xml])

    resultado = generar_reporte_cfdi_job.invoke({"job_id": job_id})
    datos = json.loads(resultado)

    assert datos["ok"] is True
    assert datos["reporte_generado"] is True
    assert datos["job_id"] == job_id
    assert (directorio_job / "reporte_cfdi.xlsx").is_file()

    jobs.eliminar_job(job_id)


def test_generar_reporte_cfdi_job_rechaza_job_inexistente() -> None:
    datos = json.loads(
        generar_reporte_cfdi_job.invoke({"job_id": "job-inexistente"})
    )

    assert datos == {"ok": False, "error": "Job CFDI no encontrado"}
