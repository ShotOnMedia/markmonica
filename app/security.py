from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import secrets

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import User, UserSession

PBKDF2_ITERATIONS = 600_000
SESSION_TTL_DAYS = 30


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations, salt_hex, digest_hex = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            bytes.fromhex(salt_hex),
            int(iterations),
        )
        return hmac.compare_digest(digest.hex(), digest_hex)
    except (ValueError, TypeError):
        return False


def new_session(db: Session, user: User) -> tuple[UserSession, str]:
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    session = UserSession(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=datetime.now(timezone.utc) + timedelta(days=SESSION_TTL_DAYS),
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session, token


def user_from_session_token(db: Session, token: str | None) -> User | None:
    if not token:
        return None
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    now = datetime.now(timezone.utc)
    stmt = (
        select(User)
        .join(UserSession, UserSession.user_id == User.id)
        .where(
            UserSession.token_hash == token_hash,
            UserSession.expires_at > now,
            User.is_active.is_(True),
        )
    )
    return db.scalar(stmt)
