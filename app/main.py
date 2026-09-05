from contextlib import asynccontextmanager
from datetime import date
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse
import hashlib
import re
import secrets
import time
import uuid

from botocore.exceptions import ClientError
from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import qrcode
from redis import Redis
from redis.exceptions import RedisError
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
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif", "image/heic", "image/heif"}
ALLOWED_VIDEO_TYPES = {"video/mp4", "video/quicktime", "video/x-m4v", "video/webm"}


def origin_for(url: str | None) -> str | None:
    if not url:
        return None
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return None
    return f"{parsed.scheme}://{parsed.netloc}"


APP_ORIGIN = origin_for(settings.app_url)
STORAGE_ORIGIN = origin_for(settings.s3_public_endpoint_url or settings.s3_endpoint_url)
COOKIE_SECURE = bool(APP_ORIGIN and APP_ORIGIN.startswith("https://"))


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


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    storage = f" {STORAGE_ORIGIN}" if STORAGE_ORIGIN else ""
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; "
        f"img-src 'self' data:{storage}; "
        f"media-src 'self'{storage}; "
        f"connect-src 'self'{storage}; "
        "style-src 'self'; script-src 'self'; font-src 'self'; "
        "frame-ancestors 'none'; base-uri 'self'; form-action 'self'",
    )
    if COOKIE_SECURE:
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response


def current_user(request: Request, db: Session) -> User | None:
    return user_from_session_token(db, request.cookies.get(SESSION_COOKIE))


def require_same_origin(request: Request) -> None:
    if not APP_ORIGIN:
        return
    origin = request.headers.get("origin")
    if origin:
        if origin.rstrip("/") != APP_ORIGIN.rstrip("/"):
            raise HTTPException(status_code=403, detail="Cross-site request rejected.")
        return
    referer = request.headers.get("referer")
    if not referer or not referer.startswith(f"{APP_ORIGIN.rstrip('/')}/"):
        raise HTTPException(status_code=403, detail="Request origin could not be verified.")


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",", 1)[0].strip()[:64]
    return (request.client.host if request.client else "unknown")[:64]


def enforce_guest_upload_rate_limit(request: Request, slug: str) -> None:
    limit = settings.guest_upload_rate_limit_per_minute
    if limit <= 0:
        return
    window = int(time.time() // 60)
    key = f"markmonica:rate:upload:{slug}:{client_ip(request)}:{window}"
    try:
        redis = Redis.from_url(settings.redis_url, socket_connect_timeout=1, socket_timeout=1)
        count = redis.incr(key)
        if count == 1:
            redis.expire(key, 120)
        if count > limit:
            raise HTTPException(status_code=429, detail="Too many upload attempts. Please wait a moment and try again.")
    except HTTPException:
        raise
    except RedisError:
        # Uploads remain available if Redis has a transient issue; readiness will
        # still report Redis degradation for operators.
        return


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
    if content_type in ALLOWED_IMAGE_TYPES:
        limit = settings.max_image_upload_mb * 1024 * 1024
    elif content_type in ALLOWED_VIDEO_TYPES:
        limit = settings.max_video_upload_mb * 1024 * 1024
    else:
        raise HTTPException(status_code=415, detail="This photo or video format is not supported.")
    if size_bytes > limit:
        raise HTTPException(status_code=413, detail="This file is larger than the event upload limit.")


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="lax",
        max_age=30 * 86400,
        path="/",
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "app": settings.app_name, "version": __version__}


@app.get("/health/ready")
def readiness() -> Response:
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
    return JSONResponse(
        {"status": "ready" if ready else "degraded", "checks": checks},
        status_code=200 if ready else 503,
    )


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse(request=request, name="index.html", context={"app_name": settings.app_name, "version": __version__, "user": None})


@app.get("/register", response_class=HTMLResponse)
def register_page(request: Request):
    return templates.TemplateResponse(request=request, name="register.html", context={"error": None})


@app.post("/register")
def register(request: Request, display_name: str = Form(...), email: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    require_same_origin(request)
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
    set_session_cookie(response, token)
    return response


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse(request=request, name="login.html", context={"error": None})


@app.post("/login")
def login(request: Request, email: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    require_same_origin(request)
    user = db.scalar(select(User).where(User.email == email.strip().lower(), User.is_active.is_(True)))
    if user is None or not verify_password(password, user.password_hash):
        return templates.TemplateResponse(request=request, name="login.html", context={"error": "Incorrect email address or password."}, status_code=401)
    _, token = new_session(db, user)
    response = RedirectResponse("/dashboard", status_code=303)
    set_session_cookie(response, token)
    return response


@app.post("/logout")
def logout(request: Request, db: Session = Depends(get_db)):
    require_same_origin(request)
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        session = db.scalar(select(UserSession).where(UserSession.token_hash == token_hash))
        if session:
            db.delete(session)
            db.commit()
    response = RedirectResponse("/", status_code=303)
    response.delete_cookie(SESSION_COOKIE, path="/")
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
    require_same_origin(request)
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
    require_same_origin(request)
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
def initiate_upload(slug: str, payload: UploadRequest, request: Request, db: Session = Depends(get_db)):
    enforce_guest_upload_rate_limit(request, slug)
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
