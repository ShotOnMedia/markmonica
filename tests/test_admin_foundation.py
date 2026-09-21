from pathlib import Path

from fastapi.testclient import TestClient

from app.admin import READY_PROCESSING_STATES, router as admin_router
from app.asgi import app
from app.models import BrandingSettings, PackageConfig, User


def test_admin_routes_are_registered():
    paths = {route.path for route in admin_router.routes if hasattr(route, "path")}
    for path in (
        "/admin", "/admin/", "/admin/users", "/admin/users/{user_id}",
        "/admin/users/{user_id}/status", "/admin/events", "/admin/events/{event_id}",
        "/admin/events/{event_id}/status", "/admin/events/{event_id}/package", "/admin/media",
        "/admin/packages", "/admin/packages/{code}", "/admin/branding",
    ):
        assert path in paths


def test_anonymous_admin_access_is_forbidden():
    with TestClient(app) as client:
        response = client.get("/admin")
    assert response.status_code == 403
    assert response.json()["detail"] == "Administrator access required."


def test_user_model_has_explicit_admin_flag():
    assert "is_admin" in User.__table__.columns
    assert User.__table__.columns["is_admin"].nullable is False


def test_package_config_model_has_managed_limits():
    for column in (
        "code", "name", "max_media_per_event", "max_storage_bytes_per_event", "max_video_bytes",
        "guest_gallery", "archive_downloads", "custom_event_design", "is_active", "tier_rank", "payment_required",
    ):
        assert column in PackageConfig.__table__.columns


def test_branding_model_has_white_label_fields():
    for column in (
        "platform_name", "support_email", "footer_text", "primary_color", "secondary_color",
        "background_color", "font_family", "logo_object_key", "favicon_object_key",
    ):
        assert column in BrandingSettings.__table__.columns


def test_ready_processing_state_is_not_pending():
    assert "ready" in READY_PROCESSING_STATES


def test_admin_templates_and_styles_exist():
    for path in (
        "templates/admin/base.html", "templates/admin/dashboard.html", "templates/admin/users.html",
        "templates/admin/user_detail.html", "templates/admin/events.html", "templates/admin/event_detail.html",
        "templates/admin/media.html", "templates/admin/packages.html", "templates/admin/branding.html", "static/admin.css",
    ):
        assert Path(path).exists()
    shell = Path("templates/admin/base.html").read_text()
    assert "Platform Admin" in shell
    assert "/admin/users" in shell
    assert "/admin/events" in shell
    assert "/admin/media" in shell
    assert "/admin/packages" in shell
    assert "/admin/branding" in shell
    assert "/brand/logo" in shell


def test_admin_mutation_routes_are_post_only():
    route_methods: dict[str, set[str]] = {}
    for route in admin_router.routes:
        if hasattr(route, "methods"):
            route_methods.setdefault(route.path, set()).update(route.methods)
    assert route_methods["/admin/users/{user_id}/status"] == {"POST"}
    assert route_methods["/admin/events/{event_id}/status"] == {"POST"}
    assert route_methods["/admin/events/{event_id}/package"] == {"POST"}
    assert route_methods["/admin/packages/{code}"] == {"POST"}
    assert route_methods["/admin/branding"] == {"GET", "POST"}
