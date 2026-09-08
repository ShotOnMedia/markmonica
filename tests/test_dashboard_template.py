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


def test_host_gallery_uses_event_scoped_media_routes():
    template = Path("templates/event_manage.html").read_text()
    base = "/events/{{ event.id }}/media/{{ item.id }}"
    assert f'{base}/download' in template
    assert f'{base}/preview' in template
    assert f'{base}/play' in template
    assert 'href="/media/{{ item.id }}"' not in template
    assert 'src="/media/{{ item.id }}' not in template
    assert 'poster="/media/{{ item.id }}' not in template
    assert 'data-original-url="/media/{{ item.id }}"' not in template
