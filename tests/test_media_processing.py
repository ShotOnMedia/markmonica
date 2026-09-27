import uuid

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db import Base
from app.models import Event, Media, User
from app.services import media_processing


def make_media(*, media_id: uuid.UUID | None = None, preview_key: str | None = None) -> Media:
    event_id = uuid.uuid4()
    return Media(
        id=media_id or uuid.uuid4(),
        event_id=event_id,
        object_key=f"events/{event_id}/originals/original.jpg",
        original_filename="memory.jpg",
        content_type="image/jpeg",
        size_bytes=100,
        status="uploaded",
        processing_status="ready",
        preview_object_key=preview_key,
    )


def test_derivative_keys_are_unique_per_media_item():
    first = make_media()
    second = make_media()

    first_key = media_processing._derivative_key(first, "preview.webp")
    second_key = media_processing._derivative_key(second, "preview.webp")

    assert first_key.endswith(f"/derivatives/{first.id}/preview.webp")
    assert second_key.endswith(f"/derivatives/{second.id}/preview.webp")
    assert first_key != second_key


def test_legacy_derivative_detection_ignores_unique_keys():
    media = make_media()
    parent = media.object_key.rsplit("/", 1)[0]

    media.preview_object_key = f"{parent}/derivatives/preview.webp"
    assert media_processing._uses_legacy_derivative_keys(media)

    media.preview_object_key = f"{parent}/derivatives/{media.id}/preview.webp"
    assert not media_processing._uses_legacy_derivative_keys(media)


def test_legacy_derivatives_are_requeued_for_automatic_repair(monkeypatch):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    test_session = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(media_processing, "SessionLocal", test_session)

    with Session(engine) as db:
        user = User(email="host@example.com", display_name="Host", password_hash="x")
        event = Event(owner=user, slug="gallery-repair", title="Gallery repair")
        legacy = make_media()
        legacy.event = event
        parent = legacy.object_key.rsplit("/", 1)[0]
        legacy.preview_object_key = f"{parent}/derivatives/preview.webp"
        current = make_media()
        current.event = event
        current.preview_object_key = media_processing._derivative_key(current, "preview.webp")
        db.add_all([user, event, legacy, current])
        db.commit()
        legacy_id = legacy.id
        current_id = current.id

    assert media_processing.requeue_legacy_derivatives() == 1

    with Session(engine) as db:
        assert db.get(Media, legacy_id).processing_status == "pending"
        assert db.get(Media, current_id).processing_status == "ready"
