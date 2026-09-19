import uuid
from datetime import date

import pytest

from app.models import Event, PackageOrder
from app.services.payments import begin_checkout, mark_failed, mark_paid, payfast_param_string, payfast_validation_url, valid_payfast_itn_signature


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


def test_payfast_param_string_preserves_itn_order_and_stops_at_signature():
    items = [("m_payment_id", "order 1"), ("item_description", ""), ("amount_gross", "500.00"), ("signature", "abc"), ("ignored", "after")]
    assert payfast_param_string(items) == "m_payment_id=order+1&item_description=&amount_gross=500.00"

def test_payfast_itn_signature_uses_return_parameter_string_with_passphrase():
    import hashlib
    items = [("m_payment_id", "order 1"), ("item_description", ""), ("amount_gross", "500.00")]
    param = "m_payment_id=order+1&item_description=&amount_gross=500.00&passphrase=checkout-passphrase"
    items.append(("signature", hashlib.md5(param.encode("utf-8")).hexdigest()))
    assert valid_payfast_itn_signature(items, "checkout-passphrase")

def test_payfast_validation_urls_are_environment_specific():
    assert payfast_validation_url(True) == "https://sandbox.payfast.co.za/eng/query/validate"
    assert payfast_validation_url(False) == "https://www.payfast.co.za/eng/query/validate"
