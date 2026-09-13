from pathlib import Path

from app.admin_system import router as system_router


def test_system_routes_are_registered():
    paths = {route.path for route in system_router.routes}
    assert "/admin/system" in paths
    assert "/admin/system/" in paths


def test_system_route_is_read_only():
    for route in system_router.routes:
        assert route.methods == {"GET"}


def test_system_template_exists():
    template = Path(__file__).resolve().parents[1] / "templates" / "admin" / "system.html"
    assert template.exists()
    content = template.read_text()
    assert "Platform health" in content
    assert "Media processing" in content
    assert "Download jobs" in content
    assert "Recent processing errors" in content


def test_system_is_active_navigation_item():
    template = Path(__file__).resolve().parents[1] / "templates" / "admin" / "base.html"
    content = template.read_text()
    assert 'href="/admin/system"' in content
    assert "System <small>Next</small>" not in content
