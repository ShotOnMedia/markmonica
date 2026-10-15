from datetime import datetime, timedelta, timezone
import hashlib

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from starlette.requests import Request

from app import admin as admin_module
from app.db import Base
from app.models import User, UserSession
from app.security import hash_password, verify_password


def make_request(cookie: str | None = None) -> Request:
    headers = [(b"cookie", f"markmonica_session={cookie}".encode())] if cookie else []
    return Request({"type": "http", "method": "POST", "path": "/admin/users/password", "headers": headers})


def make_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def add_session(db: Session, user: User, token: str) -> None:
    db.add(UserSession(
        user_id=user.id,
        token_hash=hashlib.sha256(token.encode()).hexdigest(),
        expires_at=datetime.now(timezone.utc) + timedelta(days=1),
    ))
    db.commit()


def test_admin_can_change_host_password_and_revoke_sessions(monkeypatch):
    db = make_session()
    admin = User(email="admin@example.com", display_name="Admin", password_hash=hash_password("old-admin"), is_admin=True)
    target = User(email="host@example.com", display_name="Host", password_hash=hash_password("old-password"))
    db.add_all([admin, target]);db.commit()
    add_session(db, target, "host-session")
    monkeypatch.setattr(admin_module, "require_admin", lambda request, session: admin)
    monkeypatch.setattr(admin_module, "require_same_origin", lambda request: None)

    response = admin_module.user_password(target.id, make_request(), "new-password", "new-password", db)

    db.refresh(target)
    assert response.status_code == 303
    assert response.headers["location"].endswith("?password_changed=1")
    assert verify_password("new-password", target.password_hash)
    assert not verify_password("old-password", target.password_hash)
    assert db.scalar(select(func.count(UserSession.id)).where(UserSession.user_id == target.id)) == 0


def test_password_mismatch_does_not_change_password_or_sessions(monkeypatch):
    db = make_session()
    admin = User(email="admin@example.com", display_name="Admin", password_hash="x", is_admin=True)
    target = User(email="host@example.com", display_name="Host", password_hash=hash_password("old-password"))
    db.add_all([admin, target]);db.commit()
    add_session(db, target, "host-session")
    original_hash = target.password_hash
    monkeypatch.setattr(admin_module, "require_admin", lambda request, session: admin)
    monkeypatch.setattr(admin_module, "require_same_origin", lambda request: None)

    response = admin_module.user_password(target.id, make_request(), "new-password", "different", db)

    db.refresh(target)
    assert response.headers["location"].endswith("?password_error=mismatch")
    assert target.password_hash == original_hash
    assert db.scalar(select(func.count(UserSession.id)).where(UserSession.user_id == target.id)) == 1


def test_admin_keeps_current_session_when_changing_own_password(monkeypatch):
    db = make_session()
    admin = User(email="admin@example.com", display_name="Admin", password_hash=hash_password("old-password"), is_admin=True)
    db.add(admin);db.commit()
    add_session(db, admin, "current-token")
    add_session(db, admin, "other-token")
    monkeypatch.setattr(admin_module, "require_admin", lambda request, session: admin)
    monkeypatch.setattr(admin_module, "require_same_origin", lambda request: None)

    admin_module.user_password(admin.id, make_request("current-token"), "new-password", "new-password", db)

    remaining = db.scalars(select(UserSession).where(UserSession.user_id == admin.id)).all()
    assert [item.token_hash for item in remaining] == [hashlib.sha256(b"current-token").hexdigest()]
