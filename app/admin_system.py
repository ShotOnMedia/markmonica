from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from redis import Redis
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app import __version__
from app.admin import READY_PROCESSING_STATES, fmt_bytes, require_admin, templates
from app.db import get_db
from app.models import ArchiveJob, Media
from app.services.storage import bucket_is_ready
from app.settings import settings

router = APIRouter(prefix="/admin/system", tags=["admin"])


def _check_redis() -> tuple[bool, int | None]:
    try:
        redis = Redis.from_url(settings.redis_url, socket_connect_timeout=1.5, socket_timeout=1.5)
        ok = bool(redis.ping())
        depth = int(redis.llen(settings.worker_queue)) if ok else None
        return ok, depth
    except Exception:
        return False, None


def _check_database(db: Session) -> bool:
    try:
        return db.scalar(text("SELECT 1")) == 1
    except Exception:
        return False


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def system(request: Request, db: Session = Depends(get_db)):
    admin = require_admin(request, db)
    now = datetime.now(timezone.utc)
    database_ok = _check_database(db)
    redis_ok, queue_depth = _check_redis()
    storage_ok = bucket_is_ready()

    processing = db.execute(
        select(Media.processing_status, func.count(Media.id))
        .group_by(Media.processing_status)
        .order_by(Media.processing_status)
    ).all()
    failed_media = db.scalar(select(func.count(Media.id)).where(Media.processing_status == "failed")) or 0
    processing_attention = sum(count for status, count in processing if status not in READY_PROCESSING_STATES)
    stale_processing = db.scalar(
        select(func.count(Media.id)).where(
            Media.processing_status.notin_(READY_PROCESSING_STATES | {"failed"}),
            Media.created_at < now - timedelta(hours=2),
        )
    ) or 0

    archive_rows = db.execute(
        select(ArchiveJob.status, func.count(ArchiveJob.id))
        .group_by(ArchiveJob.status)
        .order_by(ArchiveJob.status)
    ).all()
    archive_total = sum(count for _, count in archive_rows)
    archive_failed = sum(count for status, count in archive_rows if status == "failed")
    archive_active = sum(count for status, count in archive_rows if status in {"queued", "processing"})

    media_count = db.scalar(select(func.count(Media.id))) or 0
    storage_total = db.scalar(select(func.coalesce(func.sum(Media.size_bytes), 0))) or 0
    recent_failures = db.scalars(
        select(Media).where(Media.processing_status == "failed").order_by(Media.created_at.desc()).limit(8)
    ).all()

    services = [
        {"name": "Database", "ok": database_ok, "detail": "PostgreSQL query succeeded" if database_ok else "Database query failed"},
        {"name": "Redis", "ok": redis_ok, "detail": f"Queue depth: {queue_depth}" if redis_ok else "Redis ping failed"},
        {"name": "Object storage", "ok": storage_ok, "detail": f"Bucket: {settings.s3_bucket}" if storage_ok else "Bucket is unavailable"},
    ]
    overall_ok = all(item["ok"] for item in services) and failed_media == 0 and stale_processing == 0

    return templates.TemplateResponse(request=request, name="admin/system.html", context={
        "admin": admin,
        "section": "system",
        "overall_ok": overall_ok,
        "services": services,
        "version": __version__,
        "environment": settings.environment,
        "app_name": settings.app_name,
        "queue_name": settings.worker_queue,
        "queue_depth": queue_depth,
        "processing": processing,
        "processing_attention": processing_attention,
        "failed_media": failed_media,
        "stale_processing": stale_processing,
        "archive_rows": archive_rows,
        "archive_total": archive_total,
        "archive_failed": archive_failed,
        "archive_active": archive_active,
        "media_count": media_count,
        "storage_label": fmt_bytes(storage_total),
        "recent_failures": recent_failures,
    })
