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
