from app.admin_analytics import router as analytics_router


def test_analytics_routes_are_registered():
    paths = {route.path for route in analytics_router.routes}
    assert "/admin/analytics" in paths
    assert "/admin/analytics/" in paths


def test_analytics_route_is_get_only():
    for route in analytics_router.routes:
        if route.path == "/admin/analytics":
            assert route.methods == {"GET"}
            return
    raise AssertionError("analytics route not found")


def test_analytics_template_exists():
    from pathlib import Path
    template = Path(__file__).resolve().parents[1] / "templates" / "admin" / "analytics.html"
    assert template.exists()
    content = template.read_text()
    assert "Uploads · last 30 days" in content
    assert "Package distribution" in content
    assert "Processing health" in content
    assert "Largest events" in content
