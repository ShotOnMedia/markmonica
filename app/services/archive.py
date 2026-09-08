import json
from datetime import timedelta
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
        candidate = f"{stem}-{n}{suffix}"; n += 1
    used.add(candidate.lower())
    return candidate


def build_archive(job_id: uuid.UUID | str) -> bool:
    job_uuid = uuid.UUID(str(job_id))
    with SessionLocal() as db:
        job = db.scalar(select(ArchiveJob).where(ArchiveJob.id == job_uuid))
        if not job or job.status == "ready": return bool(job)
        job.status = "processing"; job.error = None; db.commit()
        try:
            query = select(Media).where(Media.event_id == job.event_id, Media.status == "uploaded").order_by(Media.created_at.asc())
            if job.requested_media_ids:
                ids = [uuid.UUID(value) for value in json.loads(job.requested_media_ids)]
                query = query.where(Media.id.in_(ids))
            media = db.scalars(query).all()
            if not media: raise ValueError("No uploaded media was available for this archive.")
            with tempfile.TemporaryDirectory(prefix="markmonica-archive-") as tmp:
                root = Path(tmp); zip_path = root / "memories.zip"; used: set[str] = set()
                with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
                    for index, item in enumerate(media):
                        local = root / f"source-{index}"
                        download_object(item.object_key, local)
                        archive.write(local, arcname=_unique_name(item.original_filename, used))
                        local.unlink(missing_ok=True)
                key = f"events/{job.event_id}/archives/{job.id}.zip"
                upload_object(zip_path, key, "application/zip")
            job.object_key = key; job.status = "ready"; job.completed_at = utcnow(); db.commit(); return True
        except Exception as exc:
            db.rollback(); job = db.scalar(select(ArchiveJob).where(ArchiveJob.id == job_uuid))
            if job: job.status = "failed"; job.error = str(exc)[:2000]; db.commit()
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
    """Delete generated ZIP objects after their retention window while keeping job history."""
    retention_hours = max(1, settings.archive_retention_hours)
    cutoff = utcnow() - timedelta(hours=retention_hours)
    with SessionLocal() as db:
        jobs = db.scalars(
            select(ArchiveJob)
            .where(
                ArchiveJob.status == "ready",
                ArchiveJob.completed_at.is_not(None),
                ArchiveJob.completed_at < cutoff,
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
        if cleaned:
            db.commit()
        return cleaned
