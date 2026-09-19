"""Serialize commercial changes per event, before locking individual orders."""
from fastapi import HTTPException
from sqlalchemy import select

from app.models import AdminActivity, Event, PackageOrder, utcnow


def lock_commercial_event(db, event_id):
    event = db.scalar(select(Event).where(Event.id == event_id)
                      .with_for_update().execution_options(populate_existing=True))
    if event is None:
        raise HTTPException(404)
    return event


def require_resolved_payments(db, event_id):
    outstanding = db.scalar(select(PackageOrder.id).where(
        PackageOrder.event_id == event_id,
        PackageOrder.status.in_(("awaiting_payment", "paid", "payment_review")),
    ).limit(1))
    if outstanding is not None:
        raise HTTPException(409, "A payment is still outstanding. Please wait for confirmation or contact support before changing packages.")


def flag_late_completed_payment(db, order: PackageOrder, provider_reference: str | None = None) -> None:
    """Quarantine a verified late payment without granting its entitlement."""
    if order.status not in {"cancelled", "failed"}:
        raise ValueError("Only a closed order can be flagged for late-payment review.")
    previous_status = order.status
    order.status = "payment_review"
    order.provider_reference = provider_reference or order.provider_reference
    order.updated_at = utcnow()
    db.add(AdminActivity(
        action="late_payment_received",
        target_type="package_order",
        target_id=str(order.id),
        target_label=f"{order.event.title} · {order.package_code}",
        detail=f"Verified COMPLETE payment received after order status {previous_status}; entitlement was not activated.",
    ))
