import re

from fastapi import APIRouter, Depends
from fastapi.responses import RedirectResponse, Response
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import BrandingSettings
from app.services.storage import create_presigned_download

router = APIRouter(tags=["branding"])

FONT_MAP = {
    "inter": ("Inter", "https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap"),
    "montserrat": ("Montserrat", "https://fonts.googleapis.com/css2?family=Montserrat:wght@400;500;600;700&display=swap"),
    "poppins": ("Poppins", "https://fonts.googleapis.com/css2?family=Poppins:wght@400;500;600;700&display=swap"),
    "playfair": ("Playfair Display", "https://fonts.googleapis.com/css2?family=Playfair+Display:wght@400;500;600;700&display=swap"),
    "cormorant": ("Cormorant Garamond", "https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@400;500;600;700&display=swap"),
    "libre-baskerville": ("Libre Baskerville", "https://fonts.googleapis.com/css2?family=Libre+Baskerville:wght@400;700&display=swap"),
}

DEFAULTS = {
    "platform_name": "Memories' Events",
    "support_email": "",
    "footer_text": "",
    "primary_color": "#a47f76",
    "secondary_color": "#302b2a",
    "background_color": "#f7f4f2",
    "font_family": "inter",
    "logo_object_key": None,
    "favicon_object_key": None,
}


def get_branding(db: Session) -> BrandingSettings | None:
    return db.get(BrandingSettings, 1)


def branding_values(db: Session) -> dict[str, object]:
    settings = get_branding(db)
    if settings is None:
        return dict(DEFAULTS)
    return {key: getattr(settings, key) for key in DEFAULTS}


def valid_hex(value: str, fallback: str) -> str:
    value = (value or "").strip().lower()
    return value if re.fullmatch(r"#[0-9a-f]{6}", value) else fallback


@router.get("/brand.css")
def brand_css(db: Session = Depends(get_db)):
    values = branding_values(db)
    font_key = str(values["font_family"])
    font_name, font_url = FONT_MAP.get(font_key, FONT_MAP["inter"])
    primary = valid_hex(str(values["primary_color"]), DEFAULTS["primary_color"])
    secondary = valid_hex(str(values["secondary_color"]), DEFAULTS["secondary_color"])
    background = valid_hex(str(values["background_color"]), DEFAULTS["background_color"])
    css = (
        f'@import url("{font_url}");\n'
        ":root{"
        f"--platform-primary:{primary};"
        f"--platform-secondary:{secondary};"
        f"--platform-background:{background};"
        f'--platform-font:"{font_name}";'
        "}\n"
        "body{font-family:var(--platform-font),ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,\"Segoe UI\",sans-serif;}\n"
    )
    return Response(css, media_type="text/css", headers={"Cache-Control": "no-store"})


@router.get("/brand/logo")
def brand_logo(db: Session = Depends(get_db)):
    settings = get_branding(db)
    if settings and settings.logo_object_key:
        return RedirectResponse(create_presigned_download(settings.logo_object_key, expires_in=900), status_code=307)
    return RedirectResponse("/static/memories-events-logo.svg", status_code=307)


@router.get("/brand/favicon")
def brand_favicon(db: Session = Depends(get_db)):
    settings = get_branding(db)
    if settings and settings.favicon_object_key:
        return RedirectResponse(create_presigned_download(settings.favicon_object_key, expires_in=900), status_code=307)
    return RedirectResponse("/static/memories-events-logo.svg", status_code=307)
