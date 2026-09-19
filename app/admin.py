from io import BytesIO
from pathlib import Path
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from urllib.parse import urlparse
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.branding import DEFAULTS as BRAND_DEFAULTS, FONT_MAP, valid_hex
from app.db import get_db
from app.models import BrandingSettings, Event, Media, PackageConfig, PackageOrder, PaymentProviderConfig, User, utcnow
from app.security import user_from_session_token
from app.services.credential_vault import encrypt_secret
from app.services.storage import delete_objects, upload_fileobj
from app.services.package_orders import lock_commercial_event, require_resolved_payments

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
router = APIRouter(prefix="/admin", tags=["admin"])
SESSION_COOKIE = "markmonica_session"
GIB = 1024**3
MIB = 1024**2
READY_PROCESSING_STATES = {"ready", "completed", "processed"}
BRAND_LOGO_TYPES = {"image/svg+xml": "svg", "image/png": "png", "image/webp": "webp", "image/jpeg": "jpg"}
BRAND_FAVICON_TYPES = {"image/svg+xml": "svg", "image/png": "png", "image/x-icon": "ico", "image/vnd.microsoft.icon": "ico"}


def admin_user(request: Request, db: Session) -> User | None:
    user = user_from_session_token(db, request.cookies.get(SESSION_COOKIE))
    return user if user and user.is_admin else None


def require_admin(request: Request, db: Session) -> User:
    user = admin_user(request, db)
    if user is None:
        raise HTTPException(403, "Administrator access required.")
    return user

def require_same_origin(request: Request) -> None:
    app_url = request.app.state.app_url if hasattr(request.app.state, "app_url") else None
    if not app_url:
        from app.settings import settings
        app_url = settings.app_url
    parsed = urlparse(app_url)
    expected = f"{parsed.scheme}://{parsed.netloc}".rstrip("/") if parsed.scheme and parsed.netloc else None
    if not expected:
        return
    origin = request.headers.get("origin")
    if origin:
        if origin.rstrip("/") != expected:
            raise HTTPException(403, "Cross-site request rejected.")
        return
    referer = request.headers.get("referer")
    if not referer or not referer.startswith(f"{expected}/"):
        raise HTTPException(403, "Request origin could not be verified.")


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


def get_or_create_branding(db: Session) -> BrandingSettings:
    branding = db.get(BrandingSettings, 1)
    if branding is None:
        branding = BrandingSettings(id=1)
        db.add(branding)
        db.flush()
    return branding


async def store_brand_asset(upload: UploadFile | None, allowed: dict[str, str], prefix: str, max_bytes: int) -> str | None:
    if upload is None or not upload.filename:
        return None
    content_type = (upload.content_type or "").lower()
    extension = allowed.get(content_type)
    if extension is None:
        raise HTTPException(415, "Unsupported branding asset type.")
    data = await upload.read(max_bytes + 1)
    if not data:
        raise HTTPException(400, "Branding assets cannot be empty.")
    if len(data) > max_bytes:
        raise HTTPException(413, "Branding asset is too large.")
    object_key = f"branding/{prefix}/{uuid.uuid4().hex}.{extension}"
    upload_fileobj(BytesIO(data), object_key, content_type)
    return object_key


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
    require_same_origin(request)
    event = lock_commercial_event(db, event_id)
    require_resolved_payments(db, event_id)
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
        select(Event.package_code, func.count(func.distinct(Event.id)), func.count(Media.id), func.coalesce(func.sum(Media.size_bytes), 0))
        .outerjoin(Media, Media.event_id == Event.id).group_by(Event.package_code)
    ).all()
    usage = {code: {"events": events, "media": media, "storage": storage} for code, events, media, storage in usage_rows}
    return templates.TemplateResponse(request=request, name="admin/packages.html", context={
        "admin": admin, "section": "packages", "packages": rows, "usage": usage,
        "fmt_bytes": fmt_bytes, "GIB": GIB, "MIB": MIB,
    })


@router.post("/packages/{code}")
def update_package(code: str, request: Request, name: str = Form(...), max_media_per_event: str = Form(""), max_storage_gb: str = Form(""), max_video_mb: str = Form(""), price_zar: str = Form("0"), guest_gallery: str | None = Form(None), archive_downloads: str | None = Form(None), custom_event_design: str | None = Form(None), is_active: str | None = Form(None), db: Session = Depends(get_db)):
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
    try:
        price = Decimal((price_zar or "0").strip()).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if price < 0:
            raise InvalidOperation
        package.price_cents = int(price * 100)
    except (InvalidOperation, ValueError):
        raise HTTPException(400, "Package price must be a valid non-negative amount.")
    package.currency = "ZAR"
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


@router.get("/package-requests", response_class=HTMLResponse)
def package_requests(request: Request, status: str = "", db: Session = Depends(get_db)):
    admin = require_admin(request, db)
    stmt = select(PackageOrder).order_by(PackageOrder.created_at.desc())
    if status in {"pending", "awaiting_payment", "paid", "approved", "failed", "cancelled"}:
        stmt = stmt.where(PackageOrder.status == status)
    orders = db.scalars(stmt.limit(250)).all()
    return templates.TemplateResponse(request=request, name="admin/package_requests.html", context={"admin": admin, "section": "package_requests", "orders": orders, "status": status})


@router.post("/package-requests/{order_id}/approve")
def approve_package_request(order_id: uuid.UUID, request: Request, db: Session = Depends(get_db)):
    require_admin(request, db)
    require_same_origin(request)
    order = db.get(PackageOrder, order_id)
    if order is None:
        raise HTTPException(404)
    lock_commercial_event(db, order.event_id)
    db.refresh(order)
    require_resolved_payments(db, order.event_id)
    if order.status != "pending":
        raise HTTPException(409, "This package request is no longer pending.")
    package = db.get(PackageConfig, order.package_code)
    if package is None or not package.is_active:
        raise HTTPException(400, "The requested package is no longer available.")
    event = db.get(Event, order.event_id)
    if event is None:
        raise HTTPException(404)
    event.package_code = package.code
    event.package_assigned_at = utcnow()
    order.status = "approved"
    order.updated_at = utcnow()
    db.commit()
    return RedirectResponse("/admin/package-requests?status=pending", status_code=303)


@router.post("/package-requests/{order_id}/cancel")
def cancel_package_request(order_id: uuid.UUID, request: Request, db: Session = Depends(get_db)):
    require_admin(request, db)
    require_same_origin(request)
    order = db.get(PackageOrder, order_id)
    if order is None:
        raise HTTPException(404)
    lock_commercial_event(db, order.event_id)
    db.refresh(order)
    if order.status != "pending":
        raise HTTPException(409, "This package request is no longer pending.")
    order.status = "cancelled"
    order.updated_at = utcnow()
    db.commit()
    return RedirectResponse("/admin/package-requests?status=pending", status_code=303)


@router.get("/settings/payments", response_class=HTMLResponse)
def payment_settings(request: Request, db: Session = Depends(get_db)):
    admin=require_admin(request,db);provider=db.get(PaymentProviderConfig,"payfast")
    if provider is None:provider=PaymentProviderConfig(code="payfast",display_name="Payfast");db.add(provider);db.commit();db.refresh(provider)
    return templates.TemplateResponse(request=request,name="admin/payment_settings.html",context={"admin":admin,"section":"payment_settings","provider":provider})

@router.post("/settings/payments/payfast")
def update_payfast_settings(request: Request,is_enabled: str|None=Form(None),is_sandbox: str|None=Form(None),merchant_id: str=Form(""),merchant_key: str=Form(""),passphrase: str=Form(""),db: Session=Depends(get_db)):
    require_admin(request,db);require_same_origin(request);provider=db.get(PaymentProviderConfig,"payfast")
    if provider is None:provider=PaymentProviderConfig(code="payfast",display_name="Payfast");db.add(provider)
    provider.is_enabled=is_enabled=="on";provider.is_sandbox=is_sandbox=="on";provider.merchant_id=merchant_id.strip() or None
    if merchant_key.strip():provider.merchant_key=encrypt_secret(merchant_key.strip())
    if passphrase.strip():provider.passphrase=encrypt_secret(passphrase.strip())
    provider.updated_at=utcnow();db.commit();return RedirectResponse("/admin/settings/payments",303)

@router.get("/branding", response_class=HTMLResponse)
def branding(request: Request, db: Session = Depends(get_db)):
    admin = require_admin(request, db)
    brand = get_or_create_branding(db)
    db.commit()
    return templates.TemplateResponse(request=request, name="admin/branding.html", context={
        "admin": admin, "section": "branding", "brand": brand, "fonts": FONT_MAP,
    })


@router.post("/branding")
async def update_branding(
    request: Request,
    platform_name: str = Form(...),
    support_email: str = Form(""),
    footer_text: str = Form(""),
    primary_color: str = Form(BRAND_DEFAULTS["primary_color"]),
    secondary_color: str = Form(BRAND_DEFAULTS["secondary_color"]),
    background_color: str = Form(BRAND_DEFAULTS["background_color"]),
    font_family: str = Form("inter"),
    logo: UploadFile | None = File(None),
    favicon: UploadFile | None = File(None),
    db: Session = Depends(get_db),
):
    require_admin(request, db)
    brand = get_or_create_branding(db)
    name = platform_name.strip()[:160]
    if not name:
        raise HTTPException(400, "Platform name is required.")
    email = support_email.strip().lower()[:320]
    if email and "@" not in email:
        raise HTTPException(400, "Support email must be a valid email address.")
    if font_family not in FONT_MAP:
        raise HTTPException(400, "Unsupported platform font.")
    brand.platform_name = name
    brand.support_email = email or None
    brand.footer_text = footer_text.strip()[:320] or None
    brand.primary_color = valid_hex(primary_color, str(BRAND_DEFAULTS["primary_color"]))
    brand.secondary_color = valid_hex(secondary_color, str(BRAND_DEFAULTS["secondary_color"]))
    brand.background_color = valid_hex(background_color, str(BRAND_DEFAULTS["background_color"]))
    brand.font_family = font_family
    new_logo = await store_brand_asset(logo, BRAND_LOGO_TYPES, "logo", 5 * MIB)
    new_favicon = await store_brand_asset(favicon, BRAND_FAVICON_TYPES, "favicon", 2 * MIB)
    old_assets = []
    if new_logo:
        old_assets.append(brand.logo_object_key)
        brand.logo_object_key = new_logo
    if new_favicon:
        old_assets.append(brand.favicon_object_key)
        brand.favicon_object_key = new_favicon
    db.commit()
    if any(old_assets):
        delete_objects(old_assets)
    return RedirectResponse("/admin/branding", status_code=303)
