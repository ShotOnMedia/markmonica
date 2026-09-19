import uuid
from datetime import date

import pytest

from app.models import Event, PackageOrder
from app.services.payments import begin_checkout, mark_failed, mark_paid


def make_order(status="pending"):
    return PackageOrder(id=uuid.uuid4(), event_id=uuid.uuid4(), user_id=uuid.uuid4(), package_code="celebration", status=status)


def make_event():
    return Event(id=uuid.uuid4(), owner_id=uuid.uuid4(), slug="test-event", title="Test Event", event_date=date.today())


def test_manual_checkout_moves_order_to_awaiting_payment():
    order = make_order()
    session = begin_checkout(order, make_event())
    assert session.provider == "manual"
    assert session.reference == str(order.id)
    assert order.status == "awaiting_payment"
    assert order.provider == "manual"


def test_paid_transition_requires_awaiting_payment():
    order = make_order("awaiting_payment")
    mark_paid(order, "provider-123")
    assert order.status == "paid"
    assert order.provider_reference == "provider-123"


def test_failed_order_can_retry_checkout():
    order = make_order("awaiting_payment")
    mark_failed(order)
    assert order.status == "failed"
    begin_checkout(order, make_event())
    assert order.status == "awaiting_payment"


def test_approved_order_cannot_restart_checkout():
    with pytest.raises(ValueError):
        begin_checkout(make_order("approved"), make_event())
