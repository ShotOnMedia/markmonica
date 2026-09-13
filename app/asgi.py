"""ASGI application assembly.

Keeping route assembly here lets platform modules stay isolated from the host/guest
application while preserving app.main for compatibility with existing tests/imports.
"""
from app.main import app
from app.admin import router as admin_router

app.include_router(admin_router)

__all__ = ["app"]
