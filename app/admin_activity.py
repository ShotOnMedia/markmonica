import uuid

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.admin import require_admin, templates
from app.db import get_db
from app.models import AdminActivity, User

router = APIRouter(prefix="/admin/activity", tags=["admin"])


def record_admin_activity(
    db: Session,
    admin: User,
    action: str,
    *,
    target_type: str | None = None,
    target_id: str | uuid.UUID | None = None,
    target_label: str | None = None,
    detail: str | None = None,
) -> AdminActivity:
    row = AdminActivity(
        admin_user_id=admin.id,
        action=action[:120],
        target_type=(target_type or None),
        target_id=(str(target_id)[:160] if target_id is not None else None),
        target_label=(target_label[:320] if target_label else None),
        detail=(detail[:1000] if detail else None),
    )
    db.add(row)
    return row


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def activity(request: Request, q: str = "", action: str = "", db: Session = Depends(get_db)):
    admin = require_admin(request, db)
    stmt = select(AdminActivity).order_by(AdminActivity.created_at.desc())
    q = q.strip()
    action = action.strip()
    if q:
        term = f"%{q}%"
        stmt = stmt.where(or_(
            AdminActivity.action.ilike(term),
            AdminActivity.target_type.ilike(term),
            AdminActivity.target_label.ilike(term),
            AdminActivity.detail.ilike(term),
        ))
    if action:
        stmt = stmt.where(AdminActivity.action == action)
    rows = db.scalars(stmt.limit(300)).all()
    actions = db.scalars(select(AdminActivity.action).distinct().order_by(AdminActivity.action)).all()
    return templates.TemplateResponse(request=request, name="admin/activity.html", context={
        "admin": admin,
        "section": "activity",
        "activity": rows,
        "actions": actions,
        "q": q,
        "action": action,
    })
