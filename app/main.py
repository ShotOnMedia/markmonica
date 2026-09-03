from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from app.settings import settings

app = FastAPI(title=settings.app_name, version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "app": settings.app_name, "version": "0.1.0"}


@app.get("/", response_class=HTMLResponse)
def home() -> str:
    return """<!doctype html><html><head><meta name='viewport' content='width=device-width,initial-scale=1'><title>MarkMonica</title><style>body{font-family:system-ui,sans-serif;margin:0;background:#f7f5f2;color:#222;display:grid;min-height:100vh;place-items:center}.card{max-width:680px;margin:24px;padding:48px;border-radius:24px;background:#fff;box-shadow:0 18px 60px #00000012;text-align:center}h1{font-size:clamp(2.5rem,8vw,5rem);margin:.1em 0}p{font-size:1.15rem;line-height:1.6;color:#666}</style></head><body><main class='card'><h1>MarkMonica</h1><p>One QR code. Every guest's memories, together.</p><p>v0.1.0 foundation is running.</p></main></body></html>"""
