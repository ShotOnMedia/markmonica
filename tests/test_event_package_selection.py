import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from starlette.requests import Request

from app import main
from app.db import Base
from app.models import Event, PackageConfig, PackageOrder, User


@pytest.fixture
def creation_context(monkeypatch):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        user = User(email="host@example.com", display_name="Host", password_hash="x")
        packages = [
            PackageConfig(code="demo", name="Demo", tier_rank=0, payment_required=False, price_cents=0),
            PackageConfig(code="starter", name="Starter", tier_rank=10, payment_required=True, price_cents=29500),
            PackageConfig(code="celebration", name="Celebration", tier_rank=20, payment_required=True, price_cents=50000),
            PackageConfig(code="premium", name="Premium", tier_rank=30, payment_required=True, price_cents=90000),
        ]
        db.add_all([user, *packages]);db.commit()
        monkeypatch.setattr(main, "current_user", lambda request, session: user)
        monkeypatch.setattr(main, "require_same_origin", lambda request: None)
        request = Request({"type": "http", "method": "POST", "path": "/", "headers": []})
        yield db, user, request
    engine.dispose()


def test_demo_selection_creates_event_without_order(creation_context):
    db, user, request = creation_context
    response = main.create_event(request, "Demo Event", "demo", "2026-10-01", db)
    event = db.scalar(select(Event).where(Event.owner_id == user.id))
    assert response.status_code == 303
    assert response.headers["location"] == f"/events/{event.id}"
    assert event.package_code == "demo"
    assert event.status == "draft"
    assert db.scalar(select(PackageOrder)) is None


def test_paid_selection_creates_demo_draft_and_pending_order(creation_context):
    db, user, request = creation_context
    response = main.create_event(request, "Paid Event", "celebration", "", db)
    event = db.scalar(select(Event).where(Event.owner_id == user.id))
    order = db.scalar(select(PackageOrder).where(PackageOrder.event_id == event.id))
    assert event.package_code == "demo"
    assert event.status == "draft"
    assert order.package_code == "celebration"
    assert order.status == "pending"
    assert order.source == "event_creation"
    assert str(order.id) in response.headers["location"]


def test_event_with_unresolved_paid_order_cannot_go_live(creation_context):
    db, user, request = creation_context
    main.create_event(request, "Paid Event", "starter", "", db)
    event = db.scalar(select(Event).where(Event.owner_id == user.id))
    with pytest.raises(HTTPException) as error:
        main.update_event(str(event.id), request, event.title, "", "live", "", "", "classic", "#7c5cff", "default", None, db)
    assert error.value.status_code == 409
    db.refresh(event)
    assert event.status == "draft"


def test_demo_event_can_be_set_live(creation_context):
    db, user, request = creation_context
    main.create_event(request, "Demo Event", "demo", "", db)
    event = db.scalar(select(Event).where(Event.owner_id == user.id))
    response = main.update_event(str(event.id), request, event.title, "", "live", "", "", "classic", "#7c5cff", "default", None, db)
    assert response.status_code == 303
    assert event.status == "live"
