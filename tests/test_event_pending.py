from datetime import date
import uuid

from fastapi import HTTPException
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from starlette.requests import Request

from app import main
from app.db import Base
from app.models import Event, User


def make_draft_event(db: Session, *, cover_object_key: str | None = None) -> Event:
    user = User(email=f"{uuid.uuid4()}@example.com", display_name="Host", password_hash="x")
    event = Event(
        owner=user,
        slug=f"celebration-{uuid.uuid4().hex[:8]}",
        title="Monica & Mark",
        event_date=date(2026, 11, 14),
        status="draft",
        cover_object_key=cover_object_key,
    )
    db.add_all([user, event])
    db.commit()
    db.refresh(event)
    return event


@pytest.fixture
def draft_context():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        yield db
    engine.dispose()


def request_for(path: str) -> Request:
    return Request({"type": "http", "method": "GET", "path": path, "headers": []})


def test_draft_event_renders_branded_pending_page_with_date(draft_context):
    event = make_draft_event(draft_context)

    response = main.guest_event(event.slug, request_for(f"/e/{event.slug}"), draft_context)
    body = response.body.decode()

    assert response.status_code == 200
    assert "Monica &amp; Mark isn’t open yet" in body
    assert "14 November 2026" in body
    assert 'src="/brand/logo"' in body
    assert "/static/event-pending.css" in body


def test_draft_event_uses_its_cover_when_available(draft_context):
    event = make_draft_event(draft_context, cover_object_key="events/example/cover.jpg")

    response = main.guest_event(event.slug, request_for(f"/e/{event.slug}"), draft_context)
    body = response.body.decode()

    assert f'src="/e/{event.slug}/cover"' in body
    assert 'src="/brand/logo"' not in body


def test_draft_cover_is_publicly_available_for_pending_page(draft_context, monkeypatch):
    event = make_draft_event(draft_context, cover_object_key="events/example/cover.jpg")
    monkeypatch.setattr(main, "create_presigned_download", lambda key: f"https://storage.example/{key}")

    response = main.guest_cover(event.slug, draft_context)

    assert response.status_code == 302
    assert response.headers["location"] == "https://storage.example/events/example/cover.jpg"


def test_draft_event_remains_blocked_from_upload_endpoints(draft_context):
    event = make_draft_event(draft_context)

    with pytest.raises(HTTPException) as error:
        main.live_event_by_slug(draft_context, event.slug)

    assert error.value.status_code == 403
