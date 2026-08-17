from fastapi.testclient import TestClient

from app.main import app


def test_health_no_ejecuta_procesos_pesados() -> None:
    respuesta = TestClient(app).get("/health")

    assert respuesta.status_code == 200
    assert respuesta.json() == {"status": "ok"}
