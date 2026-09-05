import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.main import app, validate_upload


def test_health_endpoint():
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["version"] == "0.2.0"


def test_homepage_has_security_headers():
    with TestClient(app) as client:
        response = client.get("/")
    assert response.status_code == 200
    assert "MarkMonica" in response.text
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]


def test_upload_validation_accepts_supported_media():
    validate_upload("image/jpeg", 1024)
    validate_upload("video/mp4", 1024)


def test_upload_validation_rejects_unsafe_or_unknown_types():
    with pytest.raises(HTTPException) as exc_info:
        validate_upload("image/svg+xml", 1024)
    assert exc_info.value.status_code == 415

    with pytest.raises(HTTPException) as exc_info:
        validate_upload("text/html", 1024)
    assert exc_info.value.status_code == 415


def test_upload_validation_rejects_empty_file():
    with pytest.raises(HTTPException) as exc_info:
        validate_upload("image/jpeg", 0)
    assert exc_info.value.status_code == 400
