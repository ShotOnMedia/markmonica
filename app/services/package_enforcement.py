from dataclasses import dataclass

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Event, Media
from app.services.packages import PackageDefinition, get_package, usage_percent


@dataclass(frozen=True)
class EventPackageUsage:
    media_count: int
    storage_bytes: int
    media_percent: float | None
    storage_percent: float | None


def event_package_usage(db: Session, event: Event) -> EventPackageUsage:
    package = get_package(event.package_code, db=db)
    media_count, storage_bytes = db.execute(
        select(func.count(Media.id), func.coalesce(func.sum(Media.size_bytes), 0)).where(
            Media.event_id == event.id,
            Media.status.in_(("pending", "uploaded")),
        )
    ).one()
    media_count = int(media_count or 0)
    storage_bytes = int(storage_bytes or 0)
    return EventPackageUsage(
        media_count=media_count,
        storage_bytes=storage_bytes,
        media_percent=usage_percent(media_count, package.max_media_per_event),
        storage_percent=usage_percent(storage_bytes, package.max_storage_bytes_per_event),
    )


def require_feature(package: PackageDefinition, feature: str, message: str) -> None:
    if not bool(getattr(package, feature, False)):
        raise HTTPException(status_code=403, detail=message)


def enforce_upload_entitlement(
    db: Session,
    event: Event,
    *,
    content_type: str,
    size_bytes: int,
) -> tuple[PackageDefinition, EventPackageUsage]:
    """Enforce package limits before a presigned upload is issued.

    PostgreSQL transaction-level advisory locking serializes upload reservations for
    one event. Pending Media rows count toward usage, so concurrent presign requests
    cannot all consume the same final package slot.
    """
    db.execute(select(func.pg_advisory_xact_lock(func.hashtext(str(event.id)))))
    package = get_package(event.package_code, db=db)
    usage = event_package_usage(db, event)

    if content_type.startswith("video/") and package.max_video_bytes is not None and size_bytes > package.max_video_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"This video exceeds the {package.name} package's maximum video size.",
        )
    if package.max_media_per_event is not None and usage.media_count >= package.max_media_per_event:
        raise HTTPException(
            status_code=409,
            detail=f"This event has reached its {package.name} package limit of {package.max_media_per_event} memories.",
        )
    if package.max_storage_bytes_per_event is not None and usage.storage_bytes + size_bytes > package.max_storage_bytes_per_event:
        raise HTTPException(
            status_code=409,
            detail=f"This upload would exceed the {package.name} package storage allowance.",
        )
    return package, usage
