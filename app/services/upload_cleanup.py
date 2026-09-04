import logging
from datetime import datetime, timedelta, timezone

from botocore.exceptions import ClientError
from sqlalchemy import select

from app.db import SessionLocal
from app.models import Media
from app.services.storage import head_object
from app.settings import settings

logger = logging.getLogger(__name__)


def _is_missing_object(exc: ClientError) -> bool:
    code = str(exc.response.get("Error", {}).get("Code", ""))
    status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
    return code in {"404", "NoSuchKey", "NotFound"} or status == 404


def cleanup_stale_uploads(now: datetime | None = None) -> dict[str, int]:
    """Recover or remove upload sessions that never reached /confirm.

    A stale session is old enough that its presigned upload window has long
    expired. If the object exists and matches the recorded size/content type,
    promote it to uploaded. If no object exists, remove the abandoned DB row.
    If an object exists but does not match, retain the row as failed for manual
    inspection rather than deleting potentially valuable guest media.
    """
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=settings.stale_upload_hours)
    stats = {"checked": 0, "recovered": 0, "removed": 0, "failed": 0, "errors": 0}

    with SessionLocal() as db:
        stale = list(
            db.scalars(
                select(Media)
                .where(Media.status == "uploading", Media.created_at < cutoff)
                .order_by(Media.created_at.asc())
            )
        )

        for media in stale:
            stats["checked"] += 1
            try:
                uploaded = head_object(media.object_key)
            except ClientError as exc:
                if _is_missing_object(exc):
                    db.delete(media)
                    stats["removed"] += 1
                    continue
                stats["errors"] += 1
                logger.exception("Unable to inspect stale upload %s", media.id)
                continue
            except Exception:
                stats["errors"] += 1
                logger.exception("Unable to inspect stale upload %s", media.id)
                continue

            actual_size = int(uploaded.get("ContentLength", 0))
            actual_type = str(uploaded.get("ContentType", "")).lower().strip()
            expected_type = media.content_type.lower().strip()
            type_matches = not actual_type or actual_type == expected_type

            if actual_size > 0 and actual_size == media.size_bytes and type_matches:
                media.status = "uploaded"
                stats["recovered"] += 1
            else:
                media.status = "failed"
                stats["failed"] += 1
                logger.warning(
                    "Stale upload %s has a mismatched object; preserving it for inspection "
                    "(expected size=%s type=%s, actual size=%s type=%s)",
                    media.id,
                    media.size_bytes,
                    expected_type,
                    actual_size,
                    actual_type,
                )

        db.commit()

    if stats["checked"]:
        logger.info(
            "Stale upload cleanup: checked=%s recovered=%s removed=%s failed=%s errors=%s",
            stats["checked"],
            stats["recovered"],
            stats["removed"],
            stats["failed"],
            stats["errors"],
        )
    return stats
