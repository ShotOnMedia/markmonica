import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.main import app, validate_upload
from app.services.packages import get_package, package_metadata


def test_health_endpoint():
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["version"] == "0.4.0"


def test_homepage_has_security_headers():
    with TestClient(app) as client:
        response = client.get("/")
    assert response.status_code == 200
    assert "Memories' Events" in response.text
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


def test_legacy_free_package_remains_unrestricted():
    package = get_package("free")
    assert package.code == "premium"
    assert package.max_media_per_event is None
    assert package.max_storage_bytes_per_event is None
    assert package.guest_gallery is True
    assert package.archive_downloads is True


def test_unknown_package_falls_back_to_safe_legacy_entitlement():
    metadata = package_metadata("not-a-real-package")
    assert metadata["code"] == "premium"
    assert metadata["limits"]["max_media_per_event"] is None
