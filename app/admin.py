from pathlib import Path
import uuid

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Event, Media, PackageConfig, User
from app.security import user_from_session_token

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
router = APIRouter(prefix="/admin", tags=["admin"])
SESSION_COOKIE = "markmonica_session"
GIB = 1024**3
MIB = 1024**2
READY_PROCESSING_STATES = {"ready", "completed", "processed"}


def admin_user(request: Request, db: Session) -> User | None:
    user = user_from_session_token(db, request.cookies.get(SESSION_COOKIE))
    return user if user and user.is_admin else None


def require_admin(request: Request, db: Session) -> User:
    user = admin_user(request, db)
    if user is None:
        raise HTTPException(403, "Administrator access required.")
    return user


def fmt_bytes(value: int | None) -> str:
    size = float(value or 0)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024
    return "0 B"


def parse_optional_limit(value: str, multiplier: int = 1) -> int | None:
    value = value.strip()
    if not value:
        return None
    try:
        number = float(value)
    except ValueError as exc:
        raise HTTPException(400, "Package limits must be numeric or blank for unlimited.") from exc
    if number < 0:
        raise HTTPException(400, "Package limits cannot be negative.")
    return int(number * multiplier)


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    user = require_admin(request, db)
    stats = {
        "users": db.scalar(select(func.count(User.id))) or 0,
        "events": db.scalar(select(func.count(Event.id))) or 0,
        "live_events": db.scalar(select(func.count(Event.id)).where(Event.status == "live")) or 0,
        "media": db.scalar(select(func.count(Media.id))) or 0,
        "storage": db.scalar(select(func.coalesce(func.sum(Media.size_bytes), 0))) or 0,
    }
    recent_users = db.scalars(select(User).order_by(User.created_at.desc()).limit(6)).all()
    recent_events = db.scalars(select(Event).order_by(Event.created_at.desc()).limit(6)).all()
    return templates.TemplateResponse(request=request, name="admin/dashboard.html", context={
        "admin": user, "section": "dashboard", "stats": stats,
        "storage_label": fmt_bytes(stats["storage"]), "recent_users": recent_users,
        "recent_events": recent_events,
    })


@router.get("/users", response_class=HTMLResponse)
def users(request: Request, q: str = "", db: Session = Depends(get_db)):
    admin = require_admin(request, db)
    stmt = select(User).order_by(User.created_at.desc())
    q = q.strip()
    if q:
        term = f"%{q}%"
        stmt = stmt.where(or_(User.email.ilike(term), User.display_name.ilike(term)))
    rows = db.scalars(stmt.limit(200)).all()
    event_counts = dict(db.execute(select(Event.owner_id, func.count(Event.id)).group_by(Event.owner_id)).all())
    return templates.TemplateResponse(request=request, name="admin/users.html", context={
        "admin": admin, "section": "users", "users": rows, "event_counts": event_counts, "q": q,
    })


@router.get("/users/{user_id}", response_class=HTMLResponse)
def user_detail(user_id: uuid.UUID, request: Request, db: Session = Depends(get_db)):
    admin = require_admin(request, db)
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(404)
    events = db.scalars(select(Event).where(Event.owner_id == target.id).order_by(Event.created_at.desc())).all()
    media_count, storage = db.execute(
        select(func.count(Media.id), func.coalesce(func.sum(Media.size_bytes), 0))
        .join(Event, Media.event_id == Event.id).where(Event.owner_id == target.id)
    ).one()
    return templates.TemplateResponse(request=request, name="admin/user_detail.html", context={
        "admin": admin, "section": "users", "target": target, "events": events,
        "media_count": media_count, "storage_label": fmt_bytes(storage),
    })


@router.post("/users/{user_id}/status")
def user_status(user_id: uuid.UUID, request: Request, is_active: str = Form(...), db: Session = Depends(get_db)):
    admin = require_admin(request, db)
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(404)
    active = is_active == "true"
    if target.id == admin.id and not active:
        raise HTTPException(400, "You cannot disable your own administrator account.")
    target.is_active = active
    db.commit()
    return RedirectResponse(f"/admin/users/{target.id}", status_code=303)


@router.get("/events", response_class=HTMLResponse)
def events(request: Request, q: str = "", status: str = "", db: Session = Depends(get_db)):
    admin = require_admin(request, db)
    stmt = select(Event).join(User, Event.owner_id == User.id).order_by(Event.created_at.desc())
    q = q.strip()
    if q:
        term = f"%{q}%"
        stmt = stmt.where(or_(Event.title.ilike(term), Event.slug.ilike(term), User.email.ilike(term)))
    if status in {"draft", "live"}:
        stmt = stmt.where(Event.status == status)
    rows = db.scalars(stmt.limit(250)).all()
    media_stats = {event_id: (count, size) for event_id, count, size in db.execute(
        select(Media.event_id, func.count(Media.id), func.coalesce(func.sum(Media.size_bytes), 0)).group_by(Media.event_id)
    ).all()}
    return templates.TemplateResponse(request=request, name="admin/events.html", context={
        "admin": admin, "section": "events", "events": rows, "media_stats": media_stats,
        "fmt_bytes": fmt_bytes, "q": q, "status": status,
    })


@router.get("/events/{event_id}", response_class=HTMLResponse)
def event_detail(event_id: uuid.UUID, request: Request, db: Session = Depends(get_db)):
    admin = require_admin(request, db)
    event = db.get(Event, event_id)
    if event is None:
        raise HTTPException(404)
    media = db.scalars(select(Media).where(Media.event_id == event.id).order_by(Media.created_at.desc()).limit(100)).all()
    storage = sum(item.size_bytes or 0 for item in media)
    counts = {
        "all": len(media),
        "photos": sum(1 for item in media if item.content_type.startswith("image/")),
        "videos": sum(1 for item in media if item.content_type.startswith("video/")),
        "processing": sum(1 for item in media if item.processing_status not in READY_PROCESSING_STATES),
    }
    packages = db.scalars(select(PackageConfig).where(PackageConfig.is_active.is_(True)).order_by(PackageConfig.code)).all()
    return templates.TemplateResponse(request=request, name="admin/event_detail.html", context={
        "admin": admin, "section": "events", "event": event, "media": media,
        "counts": counts, "storage_label": fmt_bytes(storage), "fmt_bytes": fmt_bytes,
        "packages": packages,
    })


@router.post("/events/{event_id}/status")
def event_status(event_id: uuid.UUID, request: Request, status: str = Form(...), db: Session = Depends(get_db)):
    require_admin(request, db)
    event = db.get(Event, event_id)
    if event is None:
        raise HTTPException(404)
    if status not in {"draft", "live"}:
        raise HTTPException(400, "Invalid event status.")
    event.status = status
    db.commit()
    return RedirectResponse(f"/admin/events/{event.id}", status_code=303)


@router.post("/events/{event_id}/package")
def event_package(event_id: uuid.UUID, request: Request, package_code: str = Form(...), db: Session = Depends(get_db)):
    require_admin(request, db)
    event = db.get(Event, event_id)
    if event is None:
        raise HTTPException(404)
    package = db.get(PackageConfig, package_code)
    if package is None or not package.is_active:
        raise HTTPException(400, "Invalid or inactive package.")
    event.package_code = package.code
    db.commit()
    return RedirectResponse(f"/admin/events/{event.id}", status_code=303)


@router.get("/media", response_class=HTMLResponse)
def media_overview(request: Request, q: str = "", processing: str = "", db: Session = Depends(get_db)):
    admin = require_admin(request, db)
    stmt = select(Media).join(Event, Media.event_id == Event.id).order_by(Media.created_at.desc())
    q = q.strip()
    if q:
        term = f"%{q}%"
        stmt = stmt.where(or_(Media.original_filename.ilike(term), Media.uploader_name.ilike(term), Event.title.ilike(term)))
    if processing:
        stmt = stmt.where(Media.processing_status == processing)
    rows = db.scalars(stmt.limit(250)).all()
    total_count = db.scalar(select(func.count(Media.id))) or 0
    total_storage = db.scalar(select(func.coalesce(func.sum(Media.size_bytes), 0))) or 0
    failed = db.scalar(select(func.count(Media.id)).where(Media.processing_status == "failed")) or 0
    return templates.TemplateResponse(request=request, name="admin/media.html", context={
        "admin": admin, "section": "media", "media": rows, "q": q, "processing": processing,
        "total_count": total_count, "storage_label": fmt_bytes(total_storage), "failed": failed, "fmt_bytes": fmt_bytes,
    })


@router.get("/packages", response_class=HTMLResponse)
def packages(request: Request, db: Session = Depends(get_db)):
    admin = require_admin(request, db)
    rows = db.scalars(select(PackageConfig).order_by(PackageConfig.code)).all()
    usage_rows = db.execute(
        select(
            Event.package_code,
            func.count(func.distinct(Event.id)),
            func.count(Media.id),
            func.coalesce(func.sum(Media.size_bytes), 0),
        )
        .outerjoin(Media, Media.event_id == Event.id)
        .group_by(Event.package_code)
    ).all()
    usage = {code: {"events": events, "media": media, "storage": storage} for code, events, media, storage in usage_rows}
    return templates.TemplateResponse(request=request, name="admin/packages.html", context={
        "admin": admin, "section": "packages", "packages": rows, "usage": usage,
        "fmt_bytes": fmt_bytes, "GIB": GIB, "MIB": MIB,
    })


@router.post("/packages/{code}")
def update_package(
    code: str,
    request: Request,
    name: str = Form(...),
    max_media_per_event: str = Form(""),
    max_storage_gb: str = Form(""),
    max_video_mb: str = Form(""),
    guest_gallery: str | None = Form(None),
    archive_downloads: str | None = Form(None),
    custom_event_design: str | None = Form(None),
    is_active: str | None = Form(None),
    db: Session = Depends(get_db),
):
    require_admin(request, db)
    package = db.get(PackageConfig, code)
    if package is None:
        raise HTTPException(404)
    clean_name = name.strip()
    if not clean_name:
        raise HTTPException(400, "Package name is required.")
    package.name = clean_name
    package.max_media_per_event = parse_optional_limit(max_media_per_event)
    package.max_storage_bytes_per_event = parse_optional_limit(max_storage_gb, GIB)
    package.max_video_bytes = parse_optional_limit(max_video_mb, MIB)
    package.guest_gallery = guest_gallery == "on"
    package.archive_downloads = archive_downloads == "on"
    package.custom_event_design = custom_event_design == "on"
    package.is_active = is_active == "on"
    if not package.is_active:
        assigned = db.scalar(select(func.count(Event.id)).where(Event.package_code == package.code)) or 0
        if assigned:
            raise HTTPException(400, "A package with assigned events cannot be disabled.")
    db.commit()
    return RedirectResponse("/admin/packages", status_code=303)
