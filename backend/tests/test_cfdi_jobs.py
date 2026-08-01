from pathlib import Path

from app.services.cfdi import jobs


def test_job_expira_y_elimina_archivos(tmp_path: Path, monkeypatch) -> None:
    directorio_job = tmp_path / "job"
    directorio_job.mkdir()
    archivo = directorio_job / "factura.xml"
    archivo.write_text("<xml />", encoding="utf-8")

    jobs.CFDI_JOBS.clear()
    monkeypatch.setattr(jobs, "JOB_TTL_SECONDS", 0)
    job_id = jobs.crear_job(directorio_job, [archivo])

    assert jobs.obtener_job(job_id) is None
    assert not directorio_job.exists()
