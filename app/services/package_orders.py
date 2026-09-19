"""Serialize commercial changes per event, before locking individual orders."""
from fastapi import HTTPException
from sqlalchemy import select

from app.models import Event, PackageOrder


def lock_commercial_event(db, event_id):
    event = db.scalar(select(Event).where(Event.id == event_id)
                      .with_for_update().execution_options(populate_existing=True))
    if event is None:
        raise HTTPException(404)
    return event


def require_resolved_payments(db, event_id):
    outstanding = db.scalar(select(PackageOrder.id).where(
        PackageOrder.event_id == event_id,
        PackageOrder.status.in_(("awaiting_payment", "paid")),
    ).limit(1))
    if outstanding is not None:
        raise HTTPException(409, "A payment is still outstanding. Please wait for confirmation or contact support before changing packages.")
