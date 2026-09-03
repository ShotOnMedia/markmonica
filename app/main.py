from contextlib import asynccontextmanager
from datetime import date
from io import BytesIO
from pathlib import Path
import hashlib
import re
import secrets

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import qrcode
from redis import Redis
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import __version__
from app.db import engine, get_db
from app.models import Event, User, UserSession
from app.security import hash_password, new_session, user_from_session_token, verify_password
from app.services.storage import bucket_is_ready, ensure_bucket
from app.settings import settings

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
SESSION_COOKIE = "markmonica_session"


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


def event_for_owner(db: Session, user: User, event_id: str) -> Event:
    event = db.scalar(select(Event).where(Event.id == event_id, Event.owner_id == user.id))
    if event is None:
        raise HTTPException(status_code=404)
    return event


def guest_url(event: Event) -> str:
    return f"{settings.app_url.rstrip('/')}/e/{event.slug}"


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
def home(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    return templates.TemplateResponse(request=request, name="index.html", context={"app_name": settings.app_name, "version": __version__, "user": user})


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
    return templates.TemplateResponse(request=request, name="event_manage.html", context={"user": user, "event": event, "guest_url": guest_url(event)})


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


@app.get("/e/{slug}", response_class=HTMLResponse)
def guest_event(slug: str, request: Request, db: Session = Depends(get_db)):
    event = db.scalar(select(Event).where(Event.slug == slug))
    if event is None:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse(request=request, name="guest_event.html", context={"event": event})
