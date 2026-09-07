from pathlib import Path


def test_dashboard_template_has_v05_host_sections():
    template = Path("templates/dashboard.html").read_text()
    assert "Host dashboard" in template
    assert "Create another celebration" in template
    assert "host-event-grid" in template
    assert "Manage event" in template
    assert "Guest page" in template


def test_dashboard_stylesheet_is_loaded():
    template = Path("templates/dashboard.html").read_text()
    assert '/static/dashboard.css' in template
    assert Path("static/dashboard.css").exists()
