import json
from datetime import datetime, timedelta
from pathlib import Path
import tempfile
import uuid
import zipfile

from sqlalchemy import select

from app.db import SessionLocal
from app.models import ArchiveJob, Media, utcnow
from app.services.storage import delete_objects, download_object, upload_object
from app.settings import settings


def _unique_name(name: str, used: set[str]) -> str:
    path = Path(name)
    stem, suffix = path.stem or "memory", path.suffix
    candidate, n = path.name, 2
    while candidate.lower() in used:
        candidate = f"{stem}-{n}{suffix}"
        n += 1
    used.add(candidate.lower())
    return candidate


def archive_expires_at(completed_at: datetime | None, retention_hours: int | None = None) -> datetime | None:
    """Return the expiry instant for a completed generated archive."""
    if completed_at is None:
        return None
    hours = max(1, retention_hours if retention_hours is not None else settings.archive_retention_hours)
    return completed_at + timedelta(hours=hours)


def archive_is_expired(completed_at: datetime | None, now: datetime | None = None, retention_hours: int | None = None) -> bool:
    expires_at = archive_expires_at(completed_at, retention_hours)
    return bool(expires_at and expires_at <= (now or utcnow()))


def build_archive(job_id: uuid.UUID | str) -> bool:
    job_uuid = uuid.UUID(str(job_id))
    with SessionLocal() as db:
        job = db.scalar(select(ArchiveJob).where(ArchiveJob.id == job_uuid))
        if not job or job.status == "ready":
            return bool(job)
        job.status = "processing"
        job.error = None
        db.commit()
        try:
            query = select(Media).where(Media.event_id == job.event_id, Media.status == "uploaded").order_by(Media.created_at.asc())
            if job.requested_media_ids:
                ids = [uuid.UUID(value) for value in json.loads(job.requested_media_ids)]
                query = query.where(Media.id.in_(ids))
            media = db.scalars(query).all()
            if not media:
                raise ValueError("No uploaded media was available for this archive.")
            with tempfile.TemporaryDirectory(prefix="markmonica-archive-") as tmp:
                root = Path(tmp)
                zip_path = root / "memories.zip"
                used: set[str] = set()
                # Photos and videos are already compressed formats, so storing them
                # avoids wasting worker CPU trying to recompress JPEG/WebP/MP4 files.
                with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_STORED) as archive:
                    for index, item in enumerate(media):
                        local = root / f"source-{index}"
                        download_object(item.object_key, local)
                        archive.write(local, arcname=_unique_name(item.original_filename, used))
                        local.unlink(missing_ok=True)
                key = f"events/{job.event_id}/archives/{job.id}.zip"
                upload_object(zip_path, key, "application/zip")
            job.object_key = key
            job.status = "ready"
            job.completed_at = utcnow()
            db.commit()
            return True
        except Exception as exc:
            db.rollback()
            job = db.scalar(select(ArchiveJob).where(ArchiveJob.id == job_uuid))
            if job:
                job.status = "failed"
                job.error = str(exc)[:2000]
                db.commit()
            return False


def process_next_archive() -> bool:
    """Recover queued archive jobs even when their Redis enqueue was missed."""
    with SessionLocal() as db:
        job_id = db.scalar(
            select(ArchiveJob.id)
            .where(ArchiveJob.status == "queued")
            .order_by(ArchiveJob.created_at.asc())
            .limit(1)
        )
    if not job_id:
        return False
    build_archive(job_id)
    return True


def cleanup_expired_archives() -> int:
    """Expire generated ZIPs and fail processing jobs stranded by a worker crash."""
    now = utcnow()
    retention_hours = max(1, settings.archive_retention_hours)
    archive_cutoff = now - timedelta(hours=retention_hours)
    stale_cutoff = now - timedelta(hours=max(1, settings.archive_stale_job_hours))

    with SessionLocal() as db:
        jobs = db.scalars(
            select(ArchiveJob)
            .where(
                ArchiveJob.status == "ready",
                ArchiveJob.completed_at.is_not(None),
                ArchiveJob.completed_at <= archive_cutoff,
                ArchiveJob.object_key.is_not(None),
            )
            .order_by(ArchiveJob.completed_at.asc())
            .limit(100)
        ).all()
        cleaned = 0
        for job in jobs:
            # Only mark the DB record expired after storage confirms deletion. If
            # storage is unavailable the ready job remains intact for a later retry.
            delete_objects([job.object_key])
            job.object_key = None
            job.status = "expired"
            cleaned += 1

        stale_jobs = db.scalars(
            select(ArchiveJob)
            .where(ArchiveJob.status == "processing", ArchiveJob.created_at <= stale_cutoff)
            .order_by(ArchiveJob.created_at.asc())
            .limit(100)
        ).all()
        for job in stale_jobs:
            job.status = "failed"
            job.error = "Archive generation was interrupted. Please generate a new download."

        if cleaned or stale_jobs:
            db.commit()
        return cleaned
