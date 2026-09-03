from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from redis import Redis
from sqlalchemy import text

from app import __version__
from app.db import engine
from app.services.storage import bucket_is_ready, ensure_bucket
from app.settings import settings

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.s3_auto_create_bucket:
        ensure_bucket()
    yield


app = FastAPI(title=settings.app_name, version=__version__, lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


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
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"app_name": settings.app_name, "version": __version__},
    )
