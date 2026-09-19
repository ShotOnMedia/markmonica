import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from starlette.requests import Request

from app import admin as admin_routes
from app.db import Base
from app.models import AdminActivity, Event, PackageConfig, PackageOrder, User
from app.services.package_orders import flag_late_completed_payment


@pytest.fixture
def order_context(monkeypatch):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        admin = User(email="admin@example.com", display_name="Admin", password_hash="x", is_admin=True)
        host = User(email="host@example.com", display_name="Host", password_hash="x")
        event = Event(owner=host, slug="order-event", title="Order Event", package_code="starter")
        package = PackageConfig(code="celebration", name="Celebration", price_cents=50000)
        db.add_all([admin, host, event, package]);db.commit()
        monkeypatch.setattr(admin_routes, "require_admin", lambda request, session: admin)
        monkeypatch.setattr(admin_routes, "require_same_origin", lambda request: None)
        request = Request({"type": "http", "method": "POST", "path": "/", "headers": []})
        yield db, admin, host, event, request
    engine.dispose()


def make_order(db, host, event, status):
    order = PackageOrder(event_id=event.id, user_id=host.id, package_code="celebration",
                         status=status, amount_cents=50000, currency="ZAR", provider="payfast")
    db.add(order);db.commit();return order


def test_admin_can_cancel_awaiting_payment_with_audited_reason(order_context):
    db, admin, host, event, request = order_context
    order = make_order(db, host, event, "awaiting_payment")
    response = admin_routes.cancel_order(order.id, request, "Confirmed abandoned at Payfast", db)
    assert response.status_code == 303
    assert order.status == "cancelled"
    activity = db.scalar(select(AdminActivity).where(AdminActivity.target_id == str(order.id)))
    assert activity.action == "order_cancelled"
    assert activity.admin_user_id == admin.id
    assert "Confirmed abandoned" in activity.detail


def test_short_reconciliation_reason_is_rejected_without_mutation(order_context):
    db, admin, host, event, request = order_context
    order = make_order(db, host, event, "awaiting_payment")
    with pytest.raises(HTTPException) as error:
        admin_routes.fail_order(order.id, request, "no", db)
    assert error.value.status_code == 400
    assert order.status == "awaiting_payment"


def test_late_payment_is_quarantined_and_does_not_activate_package(order_context):
    db, admin, host, event, request = order_context
    order = make_order(db, host, event, "cancelled")
    flag_late_completed_payment(db, order, "PF-LATE-123");db.commit()
    assert order.status == "payment_review"
    assert order.provider_reference == "PF-LATE-123"
    assert event.package_code == "starter"
    activity = db.scalar(select(AdminActivity).where(AdminActivity.target_id == str(order.id)))
    assert activity.action == "late_payment_received"


def test_reviewed_payment_activation_is_audited(order_context):
    db, admin, host, event, request = order_context
    order = make_order(db, host, event, "payment_review")
    response = admin_routes.activate_reviewed_payment(order.id, request, "Payment verified in Payfast", db)
    assert response.status_code == 303
    assert order.status == "approved"
    assert event.package_code == "celebration"
    activity = db.scalar(select(AdminActivity).where(AdminActivity.target_id == str(order.id)))
    assert activity.action == "reviewed_payment_activated"
