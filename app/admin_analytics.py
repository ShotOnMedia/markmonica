from collections import Counter
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.admin import READY_PROCESSING_STATES, fmt_bytes, require_admin, templates
from app.db import get_db
from app.models import Event, Media, PackageConfig, User

router = APIRouter(prefix="/admin/analytics", tags=["admin"])


def _day(value: datetime) -> str:
    return value.date().isoformat()


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def analytics(request: Request, db: Session = Depends(get_db)):
    admin = require_admin(request, db)
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=29)

    users_total = db.scalar(select(func.count(User.id))) or 0
    events_total = db.scalar(select(func.count(Event.id))) or 0
    live_events = db.scalar(select(func.count(Event.id)).where(Event.status == "live")) or 0
    media_total = db.scalar(select(func.count(Media.id))) or 0
    storage_total = db.scalar(select(func.coalesce(func.sum(Media.size_bytes), 0))) or 0
    failed_total = db.scalar(select(func.count(Media.id)).where(Media.processing_status == "failed")) or 0

    recent_users = db.scalars(select(User).where(User.created_at >= start).order_by(User.created_at)).all()
    recent_events = db.scalars(select(Event).where(Event.created_at >= start).order_by(Event.created_at)).all()
    recent_media = db.scalars(select(Media).where(Media.created_at >= start).order_by(Media.created_at)).all()

    user_days = Counter(_day(item.created_at) for item in recent_users)
    event_days = Counter(_day(item.created_at) for item in recent_events)
    media_days = Counter(_day(item.created_at) for item in recent_media)
    storage_days = Counter()
    for item in recent_media:
        storage_days[_day(item.created_at)] += item.size_bytes or 0

    days = [(start + timedelta(days=i)).date() for i in range(30)]
    daily = [{
        "date": day,
        "label": day.strftime("%d %b"),
        "users": user_days[day.isoformat()],
        "events": event_days[day.isoformat()],
        "media": media_days[day.isoformat()],
        "storage": storage_days[day.isoformat()],
    } for day in days]

    max_uploads = max([row["media"] for row in daily] + [1])
    max_storage = max([row["storage"] for row in daily] + [1])
    for row in daily:
        row["upload_pct"] = max(2, round(row["media"] / max_uploads * 100)) if row["media"] else 0
        row["storage_pct"] = max(2, round(row["storage"] / max_storage * 100)) if row["storage"] else 0
        row["storage_label"] = fmt_bytes(row["storage"])

    package_rows = db.execute(
        select(Event.package_code, func.count(Event.id)).group_by(Event.package_code).order_by(Event.package_code)
    ).all()
    package_names = {item.code: item.name for item in db.scalars(select(PackageConfig)).all()}
    max_package = max([count for _, count in package_rows] + [1])
    packages = [{
        "code": code,
        "name": package_names.get(code, code.title()),
        "count": count,
        "pct": round(count / max_package * 100),
    } for code, count in package_rows]

    processing_rows = db.execute(
        select(Media.processing_status, func.count(Media.id)).group_by(Media.processing_status).order_by(Media.processing_status)
    ).all()
    processing = [{"status": status or "unknown", "count": count} for status, count in processing_rows]
    processing_attention = sum(count for status, count in processing_rows if status not in READY_PROCESSING_STATES)

    largest_events = db.execute(
        select(Event.id, Event.title, Event.package_code, func.count(Media.id), func.coalesce(func.sum(Media.size_bytes), 0))
        .outerjoin(Media, Media.event_id == Event.id)
        .group_by(Event.id, Event.title, Event.package_code)
        .order_by(func.coalesce(func.sum(Media.size_bytes), 0).desc())
        .limit(8)
    ).all()

    return templates.TemplateResponse(request=request, name="admin/analytics.html", context={
        "admin": admin,
        "section": "analytics",
        "stats": {
            "users": users_total,
            "events": events_total,
            "live_events": live_events,
            "media": media_total,
            "storage": storage_total,
            "failed": failed_total,
            "processing_attention": processing_attention,
            "new_users": len(recent_users),
            "new_events": len(recent_events),
            "new_media": len(recent_media),
        },
        "storage_label": fmt_bytes(storage_total),
        "daily": daily,
        "packages": packages,
        "processing": processing,
        "largest_events": largest_events,
        "fmt_bytes": fmt_bytes,
    })
