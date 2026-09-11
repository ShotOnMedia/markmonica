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


def test_guest_font_customization_is_wired_into_host_and_guest_templates():
    manage = Path("templates/event_manage.html").read_text()
    guest = Path("templates/guest_event.html").read_text()
    css = Path("static/event-fonts.css")
    assert 'name="guest_font"' in manage
    assert 'data-font-picker' in manage
    assert 'value="great-vibes"' in manage
    assert 'data-display-font="{{ event.guest_font or \'default\' }}"' in manage
    assert 'data-display-font="{{ event.guest_font or \'default\' }}"' in guest
    assert 'fonts.googleapis.com/css2' in manage
    assert 'fonts.googleapis.com/css2' in guest
    assert css.exists()
    styles = css.read_text()
    assert 'Great Vibes' in styles
    assert 'Playfair Display' in styles
    assert '.guest-event-intro h1' in styles


def test_public_homepage_has_product_ctas_and_sections():
    template = Path("templates/index.html").read_text()
    assert '/static/home.css' in template
    assert 'Create your event' in template
    assert 'See how it works' in template
    assert 'How it works' in template
    assert 'Simple for guests. Useful for hosts.' in template
    assert 'href="/register"' in template
    assert 'href="/login"' in template
    assert Path("static/home.css").exists()
