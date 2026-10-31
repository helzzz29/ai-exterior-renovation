from fastapi.testclient import TestClient

from app.main import app


def test_health() -> None:
    assert TestClient(app).get("/api/health").json() == {"status": "ok"}


def test_openapi_builds() -> None:
    schema = app.openapi()
    assert "/api/projects/{project_id}/photo" in schema["paths"]
