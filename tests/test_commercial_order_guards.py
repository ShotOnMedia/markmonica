import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from starlette.requests import Request

from app import main
from app.db import Base
from app.models import Event, PackageConfig, PackageOrder, User


@pytest.fixture
def context(monkeypatch):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        user = User(email="host@example.com", display_name="Host", password_hash="x")
        event = Event(owner=user, slug="test-event", title="Event", package_code="starter")
        db.add_all([user, event, PackageConfig(code="celebration", name="Celebration", price_cents=50000),
                    PackageConfig(code="premium", name="Premium", price_cents=90000)])
        db.commit()
        monkeypatch.setattr(main, "current_user", lambda request, session: user)
        monkeypatch.setattr(main, "require_same_origin", lambda request: None)
        request = Request({"type": "http", "method": "POST", "path": "/", "headers": []})
        yield db, user, event, request
    engine.dispose()


def add_order(db, user, event, status):
    order = PackageOrder(event_id=event.id, user_id=user.id, package_code="celebration",
                         status=status, amount_cents=50000, currency="ZAR", provider="payfast")
    db.add(order)
    db.commit()
    return order


@pytest.mark.parametrize("status", ["awaiting_payment", "paid"])
def test_outstanding_payment_blocks_package_change(context, status):
    db, user, event, request = context
    order = add_order(db, user, event, status)
    with pytest.raises(HTTPException) as error:
        main.package_request(str(event.id), request, "premium", db)
    assert error.value.status_code == 409
    assert order.package_code == "celebration"
    assert event.package_code == "starter"


def test_pending_selection_reuses_order_without_granting_entitlements(context):
    db, user, event, request = context
    order = add_order(db, user, event, "pending")
    response = main.package_request(str(event.id), request, "premium", db)
    assert response.status_code == 303
    assert str(order.id) in response.headers["location"]
    assert order.package_code == "premium"
    assert order.amount_cents == 90000
    assert event.package_code == "starter"
    assert len(db.scalars(select(PackageOrder)).all()) == 1


@pytest.mark.parametrize("status", ["approved", "paid", "cancelled", "failed", "awaiting_payment"])
def test_checkout_does_not_reset_existing_state(context, status):
    db, user, event, request = context
    order = add_order(db, user, event, status)
    with pytest.raises(HTTPException) as error:
        main.start_checkout(str(event.id), order.id, request, db)
    assert error.value.status_code == 409
    assert order.status == status


def test_cancel_return_keeps_payment_outstanding(context):
    db, user, event, request = context
    order = add_order(db, user, event, "awaiting_payment")
    response = main.payfast_cancel(order.id, request, db)
    assert response.status_code == 303
    db.refresh(order)
    assert order.status == "awaiting_payment"


def test_zero_price_cannot_start_checkout(context):
    db, user, event, request = context
    order = add_order(db, user, event, "pending")
    order.amount_cents = 0
    db.commit()
    with pytest.raises(HTTPException) as error:
        main.start_checkout(str(event.id), order.id, request, db)
    assert error.value.status_code == 400
    assert order.status == "pending"
