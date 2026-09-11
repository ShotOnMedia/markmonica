from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.services.archive import archive_expires_at, archive_is_expired


def test_archive_expiry_uses_retention_window():
    completed = datetime(2026, 9, 11, 12, 0, tzinfo=timezone.utc)
    assert archive_expires_at(completed, 48) == completed + timedelta(hours=48)
    assert not archive_is_expired(completed, completed + timedelta(hours=47, minutes=59), 48)
    assert archive_is_expired(completed, completed + timedelta(hours=48), 48)


def test_incomplete_archive_has_no_expiry():
    assert archive_expires_at(None, 48) is None
    assert not archive_is_expired(None, retention_hours=48)


def test_archive_worker_accepts_web_queue_key():
    worker = Path("worker/main.py").read_text()
    assert 'job.get("job_id") or job.get("archive_job_id")' in worker


def test_archive_download_helper_supports_response_filename():
    storage = Path("app/services/storage.py").read_text()
    assert "ResponseContentDisposition" in storage


def test_archive_routes_expose_expiry_and_friendly_expired_page():
    app = Path("app/main.py").read_text()
    assert '"expires_at":expires_at.isoformat() if expires_at else None' in app
    assert '"expires_in_seconds":expires_in_seconds' in app
    assert 'name="archive_expired.html"' in app
    assert 'status_code=410' in app
    assert 'response_filename=filename' in app
    template = Path("templates/archive_expired.html").read_text()
    assert "This download has expired" in template
    assert "Your original photos and videos are still safe" in template


def test_gallery_reports_archive_retention_to_host():
    gallery = Path("static/gallery.js").read_text()
    assert "available ${expiryLabel(job.expires_in_seconds)}" in gallery
    assert "job.status==='expired'" in gallery
