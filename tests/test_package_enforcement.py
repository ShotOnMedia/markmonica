import uuid
from pathlib import Path

from fastapi import HTTPException
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base
from app.models import Event, Media, PackageConfig, User
from app.services.package_enforcement import (
    enforce_upload_entitlement,
    event_package_usage,
    require_feature,
)
from app.services.packages import PACKAGES


def make_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def make_event(db: Session, package_code: str = "starter") -> Event:
    user = User(email=f"{uuid.uuid4()}@example.com", display_name="Host", password_hash="x")
    event = Event(owner=user, slug=f"event-{uuid.uuid4().hex[:8]}", title="Event", status="live", package_code=package_code)
    db.add_all([user, event])
    db.commit()
    db.refresh(event)
    return event


def add_media(db: Session, event: Event, *, size_bytes: int, status: str = "pending", content_type: str = "image/jpeg") -> Media:
    media = Media(
        event_id=event.id,
        object_key=f"events/{event.id}/originals/{uuid.uuid4().hex}",
        original_filename="memory.jpg",
        content_type=content_type,
        size_bytes=size_bytes,
        status=status,
        processing_status="pending",
    )
    db.add(media)
    db.commit()
    return media


def test_starter_disables_guest_gallery():
    with pytest.raises(HTTPException) as exc:
        require_feature(PACKAGES["starter"], "guest_gallery", "Guest gallery unavailable")
    assert exc.value.status_code == 403


def test_celebration_allows_guest_gallery():
    require_feature(PACKAGES["celebration"], "guest_gallery", "Guest gallery unavailable")


def test_premium_remains_unlimited_for_media_and_storage():
    premium = PACKAGES["premium"]
    assert premium.max_media_per_event is None
    assert premium.max_storage_bytes_per_event is None


def test_starter_limits_are_enforceable():
    starter = PACKAGES["starter"]
    assert starter.max_media_per_event == 100
    assert starter.max_storage_bytes_per_event == 1024**3
    assert starter.max_video_bytes == 500 * 1024**2


def test_pending_and_uploaded_media_both_reserve_quota():
    db = make_session()
    event = make_event(db)
    add_media(db, event, size_bytes=10, status="pending")
    add_media(db, event, size_bytes=20, status="uploaded")
    add_media(db, event, size_bytes=30, status="failed")

    usage = event_package_usage(db, event)

    assert usage.media_count == 2
    assert usage.storage_bytes == 30


def test_db_managed_count_limit_blocks_next_reservation():
    db = make_session()
    event = make_event(db)
    db.add(PackageConfig(
        code="starter",
        name="Starter",
        max_media_per_event=2,
        max_storage_bytes_per_event=10_000,
        max_video_bytes=5_000,
        guest_gallery=False,
        archive_downloads=True,
        custom_event_design=True,
        is_active=True,
    ))
    db.commit()
    add_media(db, event, size_bytes=100)
    add_media(db, event, size_bytes=100)

    with pytest.raises(HTTPException) as exc:
        enforce_upload_entitlement(db, event, content_type="image/jpeg", size_bytes=100)

    assert exc.value.status_code == 409
    assert "2-memory Starter package limit" in exc.value.detail


def test_db_managed_storage_limit_blocks_upload_that_would_overrun_allowance():
    db = make_session()
    event = make_event(db)
    db.add(PackageConfig(
        code="starter",
        name="Starter",
        max_media_per_event=10,
        max_storage_bytes_per_event=1_000,
        max_video_bytes=5_000,
        guest_gallery=False,
        archive_downloads=True,
        custom_event_design=True,
        is_active=True,
    ))
    db.commit()
    add_media(db, event, size_bytes=800)

    with pytest.raises(HTTPException) as exc:
        enforce_upload_entitlement(db, event, content_type="image/jpeg", size_bytes=250)

    assert exc.value.status_code == 409
    assert "storage allowance" in exc.value.detail


def test_db_managed_video_limit_is_enforced():
    db = make_session()
    event = make_event(db)
    db.add(PackageConfig(
        code="starter",
        name="Starter",
        max_media_per_event=10,
        max_storage_bytes_per_event=10_000,
        max_video_bytes=500,
        guest_gallery=False,
        archive_downloads=True,
        custom_event_design=True,
        is_active=True,
    ))
    db.commit()

    with pytest.raises(HTTPException) as exc:
        enforce_upload_entitlement(db, event, content_type="video/mp4", size_bytes=501)

    assert exc.value.status_code == 413
    assert "Starter package" in exc.value.detail


def test_route_and_template_wiring_is_present():
    main = Path("app/main.py").read_text()
    manage = Path("templates/event_manage.html").read_text()
    guest = Path("templates/guest_event.html").read_text()

    assert "enforce_upload_entitlement(db,event" in main
    assert 'require_feature(package,"archive_downloads"' in main
    assert 'require_feature(package,"custom_event_design"' in main
    assert "package.guest_gallery and guest_gallery_enabled" in main
    assert '"package_usage":usage' in main
    assert "Package & usage" in manage
    assert "package_usage.media_count" in manage
    assert "package.archive_downloads" in manage
    assert "guest_gallery_enabled" in guest
