from pathlib import Path

from app.admin_activity import router as activity_router
from app.models import AdminActivity


def test_activity_routes_are_registered():
    paths = {route.path for route in activity_router.routes}
    assert "/admin/activity" in paths
    assert "/admin/activity/" in paths


def test_activity_route_is_get_only():
    for route in activity_router.routes:
        if route.path == "/admin/activity":
            assert route.methods == {"GET"}
            return
    raise AssertionError("activity route not found")


def test_activity_model_fields():
    columns = set(AdminActivity.__table__.columns.keys())
    assert {"id", "admin_user_id", "action", "target_type", "target_id", "target_label", "detail", "created_at"} <= columns


def test_activity_template_exists():
    template = Path(__file__).resolve().parents[1] / "templates" / "admin" / "activity.html"
    assert template.exists()
    content = template.read_text()
    assert "Administrator activity" in content
    assert "All actions" in content


def test_activity_navigation_exists():
    template = Path(__file__).resolve().parents[1] / "templates" / "admin" / "base.html"
    content = template.read_text()
    assert 'href="/admin/activity"' in content
    assert "Activity log" in content


def test_audit_middleware_maps_admin_mutations():
    from app.admin_audit_middleware import _describe
    class DummyDB:
        def get(self, model, key):
            return None
    db = DummyDB()
    assert _describe("/admin/branding", db)[0] == "branding_updated"
    assert _describe("/admin/packages/starter", db)[0] == "package_updated"
    assert _describe("/admin/events/00000000-0000-0000-0000-000000000001/status", db)[0] == "event_status_changed"
    assert _describe("/admin/events/00000000-0000-0000-0000-000000000001/package", db)[0] == "event_package_changed"
    assert _describe("/admin/users/00000000-0000-0000-0000-000000000001/status", db)[0] == "user_status_changed"
