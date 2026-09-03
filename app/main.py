from contextlib import asynccontextmanager
from datetime import date
from io import BytesIO
from pathlib import Path
import hashlib
import re
import secrets
import uuid

from botocore.exceptions import ClientError
from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import qrcode
from redis import Redis
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import __version__
from app.db import engine, get_db
from app.models import Event, Media, User, UserSession
from app.security import hash_password, new_session, user_from_session_token, verify_password
from app.services.storage import (
    bucket_is_ready,
    create_presigned_download,
    create_presigned_upload,
    ensure_bucket,
    head_object,
)
from app.settings import settings

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
SESSION_COOKIE = "markmonica_session"


class UploadRequest(BaseModel):
    filename: str
    content_type: str
    size_bytes: int
    guest_name: str | None = None


class UploadConfirmRequest(BaseModel):
    media_id: uuid.UUID


@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.s3_auto_create_bucket:
        ensure_bucket()
    yield


app = FastAPI(title=settings.app_name, version=__version__, lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


def current_user(request: Request, db: Session) -> User | None:
    return user_from_session_token(db, request.cookies.get(SESSION_COOKIE))


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")[:90]
    return slug or "event"


def safe_filename(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", Path(value).name).strip("-.")
    return cleaned[:180] or "upload"


def event_for_owner(db: Session, user: User, event_id: str) -> Event:
    event = db.scalar(select(Event).where(Event.id == event_id, Event.owner_id == user.id))
    if event is None:
        raise HTTPException(status_code=404)
    return event


def live_event_by_slug(db: Session, slug: str) -> Event:
    event = db.scalar(select(Event).where(Event.slug == slug))
    if event is None:
        raise HTTPException(status_code=404)
    if event.status != "live":
        raise HTTPException(status_code=403, detail="This event is not accepting uploads yet.")
    return event


def guest_url(event: Event) -> str:
    return f"{settings.app_url.rstrip('/')}/e/{event.slug}"


def validate_upload(content_type: str, size_bytes: int) -> None:
    if size_bytes <= 0:
        raise HTTPException(status_code=400, detail="Empty files cannot be uploaded.")
    if content_type.startswith("image/"):
        limit = settings.max_image_upload_mb * 1024 * 1024
    elif content_type.startswith("video/"):
        limit = settings.max_video_upload_mb * 1024 * 1024
    else:
        raise HTTPException(status_code=415, detail="Only photos and videos are supported.")
    if size_bytes > limit:
        raise HTTPException(status_code=413, detail="This file is larger than the event upload limit.")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "app": settings.app_name, "version": __version__}


@app.get("/health/ready")
def readiness() -> dict[str, object]:
    checks = {"database": False, "redis": False, "storage": False}
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        checks["database"] = True
    except Exception:
        pass
    try:
        client = Redis.from_url(settings.redis_url, socket_connect_timeout=2, socket_timeout=2)
        checks["redis"] = bool(client.ping())
    except Exception:
        pass
    checks["storage"] = bucket_is_ready()
    ready = all(checks.values())
    return {"status": "ready" if ready else "degraded", "checks": checks}


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse(request=request, name="index.html", context={"app_name": settings.app_name, "version": __version__, "user": None})


@app.get("/register", response_class=HTMLResponse)
def register_page(request: Request):
    return templates.TemplateResponse(request=request, name="register.html", context={"error": None})


@app.post("/register")
def register(request: Request, display_name: str = Form(...), email: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    email = email.strip().lower()
    display_name = display_name.strip()
    if len(password) < 8 or not display_name or "@" not in email:
        return templates.TemplateResponse(request=request, name="register.html", context={"error": "Please enter a name, valid email address and a password of at least 8 characters."}, status_code=400)
    user = User(email=email, display_name=display_name, password_hash=hash_password(password))
    db.add(user)
    try:
        db.commit()
        db.refresh(user)
    except IntegrityError:
        db.rollback()
        return templates.TemplateResponse(request=request, name="register.html", context={"error": "An account with that email address already exists."}, status_code=409)
    _, token = new_session(db, user)
    response = RedirectResponse("/dashboard", status_code=303)
    response.set_cookie(SESSION_COOKIE, token, httponly=True, secure=request.url.scheme == "https", samesite="lax", max_age=30 * 86400)
    return response


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse(request=request, name="login.html", context={"error": None})


@app.post("/login")
def login(request: Request, email: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == email.strip().lower(), User.is_active.is_(True)))
    if user is None or not verify_password(password, user.password_hash):
        return templates.TemplateResponse(request=request, name="login.html", context={"error": "Incorrect email address or password."}, status_code=401)
    _, token = new_session(db, user)
    response = RedirectResponse("/dashboard", status_code=303)
    response.set_cookie(SESSION_COOKIE, token, httponly=True, secure=request.url.scheme == "https", samesite="lax", max_age=30 * 86400)
    return response


@app.post("/logout")
def logout(request: Request, db: Session = Depends(get_db)):
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        session = db.scalar(select(UserSession).where(UserSession.token_hash == token_hash))
        if session:
            db.delete(session)
            db.commit()
    response = RedirectResponse("/", status_code=303)
    response.delete_cookie(SESSION_COOKIE)
    return response


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    events = db.scalars(select(Event).where(Event.owner_id == user.id).order_by(Event.created_at.desc())).all()
    return templates.TemplateResponse(request=request, name="dashboard.html", context={"user": user, "events": events, "error": None})


@app.post("/events")
def create_event(request: Request, title: str = Form(...), event_date: str = Form(""), db: Session = Depends(get_db)):
    user = current_user(request, db)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    title = title.strip()
    if not title:
        return RedirectResponse("/dashboard", status_code=303)
    try:
        parsed_date = date.fromisoformat(event_date) if event_date else None
    except ValueError:
        parsed_date = None
    event = Event(owner_id=user.id, title=title, event_date=parsed_date, slug=f"{slugify(title)}-{secrets.token_hex(3)}")
    db.add(event)
    db.commit()
    db.refresh(event)
    return RedirectResponse(f"/events/{event.id}", status_code=303)


@app.get("/events/{event_id}", response_class=HTMLResponse)
def manage_event(event_id: str, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    event = event_for_owner(db, user, event_id)
    media = db.scalars(select(Media).where(Media.event_id == event.id, Media.status == "uploaded").order_by(Media.created_at.desc())).all()
    return templates.TemplateResponse(request=request, name="event_manage.html", context={"user": user, "event": event, "guest_url": guest_url(event), "media": media})


@app.post("/events/{event_id}")
def update_event(event_id: str, request: Request, title: str = Form(...), event_date: str = Form(""), status: str = Form("draft"), db: Session = Depends(get_db)):
    user = current_user(request, db)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    event = event_for_owner(db, user, event_id)
    event.title = title.strip() or event.title
    try:
        event.event_date = date.fromisoformat(event_date) if event_date else None
    except ValueError:
        pass
    event.status = "live" if status == "live" else "draft"
    db.commit()
    return RedirectResponse(f"/events/{event.id}", status_code=303)


@app.get("/events/{event_id}/qr.png")
def event_qr(event_id: str, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if user is None:
        raise HTTPException(status_code=401)
    event = event_for_owner(db, user, event_id)
    image = qrcode.make(guest_url(event))
    output = BytesIO()
    image.save(output, format="PNG")
    return Response(output.getvalue(), media_type="image/png", headers={"Content-Disposition": f'inline; filename="{event.slug}-qr.png"'})


@app.get("/media/{media_id}")
def view_media(media_id: uuid.UUID, request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    media = db.scalar(select(Media).join(Event).where(Media.id == media_id, Event.owner_id == user.id, Media.status == "uploaded"))
    if media is None:
        raise HTTPException(status_code=404)
    return RedirectResponse(create_presigned_download(media.object_key), status_code=302)


@app.get("/e/{slug}", response_class=HTMLResponse)
def guest_event(slug: str, request: Request, db: Session = Depends(get_db)):
    event = db.scalar(select(Event).where(Event.slug == slug))
    if event is None:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse(request=request, name="guest_event.html", context={"event": event, "max_image_mb": settings.max_image_upload_mb, "max_video_mb": settings.max_video_upload_mb})


@app.post("/api/events/{slug}/uploads")
def initiate_upload(slug: str, payload: UploadRequest, db: Session = Depends(get_db)):
    event = live_event_by_slug(db, slug)
    content_type = payload.content_type.lower().strip()
    validate_upload(content_type, payload.size_bytes)
    filename = safe_filename(payload.filename)
    object_key = f"events/{event.id}/{uuid.uuid4().hex}/{filename}"
    media = Media(
        event_id=event.id,
        object_key=object_key,
        original_filename=filename,
        content_type=content_type,
        size_bytes=payload.size_bytes,
        uploader_name=(payload.guest_name or "").strip()[:160] or None,
        status="uploading",
    )
    db.add(media)
    db.commit()
    db.refresh(media)
    upload_url = create_presigned_upload(object_key, content_type)
    return {"media_id": str(media.id), "upload_url": upload_url, "content_type": content_type, "expires_in": settings.upload_url_expiry_seconds}


@app.post("/api/events/{slug}/uploads/confirm")
def confirm_upload(slug: str, payload: UploadConfirmRequest, db: Session = Depends(get_db)):
    event = live_event_by_slug(db, slug)
    media = db.scalar(select(Media).where(Media.id == payload.media_id, Media.event_id == event.id, Media.status == "uploading"))
    if media is None:
        raise HTTPException(status_code=404, detail="Upload session not found.")
    try:
        uploaded = head_object(media.object_key)
    except ClientError as exc:
        raise HTTPException(status_code=409, detail="The uploaded object could not be verified yet.") from exc
    actual_size = int(uploaded.get("ContentLength", 0))
    actual_type = str(uploaded.get("ContentType", "")).lower()
    if actual_size <= 0 or actual_size != media.size_bytes or (actual_type and actual_type != media.content_type.lower()):
        raise HTTPException(status_code=409, detail="The uploaded object does not match the requested file.")
    media.status = "uploaded"
    db.commit()
    return {"status": "uploaded", "media_id": str(media.id)}
