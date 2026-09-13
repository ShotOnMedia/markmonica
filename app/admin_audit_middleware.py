import uuid

from fastapi import Request

from app.admin_activity import record_admin_activity
from app.db import SessionLocal
from app.models import Event, PackageConfig, User
from app.security import user_from_session_token

SESSION_COOKIE = "markmonica_session"


def _describe(path: str, db):
    parts = [part for part in path.split("/") if part]
    if path == "/admin/branding":
        return "branding_updated", "platform", "branding", "Platform branding", "Branding settings were updated."
    if len(parts) >= 3 and parts[1] == "packages":
        code = parts[2]
        package = db.get(PackageConfig, code)
        label = package.name if package else code.title()
        return "package_updated", "package", code, label, "Package configuration was updated."
    if len(parts) >= 4 and parts[1] == "users" and parts[3] == "status":
        try:
            target = db.get(User, uuid.UUID(parts[2]))
        except ValueError:
            target = None
        label = target.email if target else parts[2]
        state = "enabled" if target and target.is_active else "disabled" if target else "changed"
        return "user_status_changed", "user", parts[2], label, f"Host account status was {state}."
    if len(parts) >= 4 and parts[1] == "events":
        try:
            event = db.get(Event, uuid.UUID(parts[2]))
        except ValueError:
            event = None
        label = event.title if event else parts[2]
        if parts[3] == "status":
            state = event.status if event else "changed"
            return "event_status_changed", "event", parts[2], label, f"Event status is now {state}."
        if parts[3] == "package":
            package = event.package_code if event else "changed"
            return "event_package_changed", "event", parts[2], label, f"Event package is now {package}."
    return "admin_change", "platform", None, path, "Administrator mutation completed successfully."


def install_admin_audit(app):
    @app.middleware("http")
    async def admin_audit(request: Request, call_next):
        response = await call_next(request)
        if request.method == "POST" and request.url.path.startswith("/admin/") and response.status_code < 400:
            try:
                with SessionLocal() as db:
                    admin = user_from_session_token(db, request.cookies.get(SESSION_COOKIE))
                    if admin and admin.is_admin:
                        action, target_type, target_id, target_label, detail = _describe(request.url.path, db)
                        record_admin_activity(
                            db, admin, action,
                            target_type=target_type,
                            target_id=target_id,
                            target_label=target_label,
                            detail=detail,
                        )
                        db.commit()
            except Exception:
                # Audit logging must never turn a successful administrator action into an error.
                pass
        return response
