"""ASGI application assembly.

Keeping route assembly here lets platform modules stay isolated from the host/guest
application while preserving app.main for compatibility with existing tests/imports.
"""
from app.main import app
from app.admin import router as admin_router
from app.admin_activity import router as activity_router
from app.admin_analytics import router as analytics_router
from app.admin_audit_middleware import install_admin_audit
from app.admin_system import router as system_router
from app.branding import router as branding_router

app.include_router(admin_router)
app.include_router(activity_router)
app.include_router(analytics_router)
app.include_router(system_router)
app.include_router(branding_router)
install_admin_audit(app)

__all__ = ["app"]
