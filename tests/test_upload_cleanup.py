import uuid
from datetime import datetime, timedelta, timezone

from botocore.exceptions import ClientError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db import Base
from app.models import Event, Media, User
from app.services import upload_cleanup


def missing_object(*_args, **_kwargs):
    raise ClientError(
        {"Error": {"Code": "NoSuchKey"}, "ResponseMetadata": {"HTTPStatusCode": 404}},
        "HeadObject",
    )


def test_stale_pending_upload_reservation_is_removed(monkeypatch):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    test_session = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(upload_cleanup, "SessionLocal", test_session)
    monkeypatch.setattr(upload_cleanup, "head_object", missing_object)

    now = datetime(2026, 9, 27, 9, 0, tzinfo=timezone.utc)
    with Session(engine) as db:
        user = User(email="cleanup@example.com", display_name="Host", password_hash="x")
        event = Event(owner=user, slug="stale-upload", title="Stale upload")
        media = Media(
            event=event,
            object_key=f"events/{uuid.uuid4()}/originals/abandoned.jpg",
            original_filename="abandoned.jpg",
            content_type="image/jpeg",
            size_bytes=100,
            status="pending",
            processing_status="pending",
            created_at=now - timedelta(hours=3),
        )
        db.add_all([user, event, media])
        db.commit()
        media_id = media.id

    stats = upload_cleanup.cleanup_stale_uploads(now=now)

    assert stats == {"checked": 1, "recovered": 0, "removed": 1, "failed": 0, "errors": 0}
    with Session(engine) as db:
        assert db.get(Media, media_id) is None


def test_recent_pending_upload_is_left_for_confirmation(monkeypatch):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    test_session = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(upload_cleanup, "SessionLocal", test_session)
    monkeypatch.setattr(upload_cleanup, "head_object", missing_object)

    now = datetime(2026, 9, 27, 9, 0, tzinfo=timezone.utc)
    with Session(engine) as db:
        user = User(email="recent@example.com", display_name="Host", password_hash="x")
        event = Event(owner=user, slug="recent-upload", title="Recent upload")
        media = Media(
            event=event,
            object_key=f"events/{uuid.uuid4()}/originals/recent.jpg",
            original_filename="recent.jpg",
            content_type="image/jpeg",
            size_bytes=100,
            status="pending",
            processing_status="pending",
            created_at=now - timedelta(minutes=30),
        )
        db.add_all([user, event, media])
        db.commit()
        media_id = media.id

    stats = upload_cleanup.cleanup_stale_uploads(now=now)

    assert stats["checked"] == 0
    with Session(engine) as db:
        assert db.get(Media, media_id) is not None
