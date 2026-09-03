from fastapi.testclient import TestClient

from app.main import app


def test_health_endpoint():
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["version"] == "0.1.0"


def test_homepage():
    with TestClient(app) as client:
        response = client.get("/")
    assert response.status_code == 200
    assert "MarkMonica" in response.text
