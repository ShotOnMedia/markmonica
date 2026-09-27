from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


GIB = 1024**3
MIB = 1024**2


@dataclass(frozen=True)
class PackageDefinition:
    code: str
    name: str
    max_events: int | None
    max_media_per_event: int | None
    max_storage_bytes_per_event: int | None
    max_video_bytes: int | None
    guest_gallery: bool
    archive_downloads: bool
    custom_event_design: bool
    tier_rank: int
    payment_required: bool


PACKAGES: dict[str, PackageDefinition] = {
    "demo": PackageDefinition("demo", "Demo", None, 20, 250 * MIB, 50 * MIB, False, False, False, 0, False),
    "starter": PackageDefinition("starter", "Starter", None, 100, 1 * GIB, 500 * MIB, False, True, True, 10, True),
    "celebration": PackageDefinition("celebration", "Celebration", None, 500, 5 * GIB, 500 * MIB, True, True, True, 20, True),
    "premium": PackageDefinition("premium", "Premium", None, None, None, 500 * MIB, True, True, True, 30, True),
}

DEFAULT_PACKAGE_CODE = "starter"
LEGACY_PACKAGE_CODE = "premium"


def _fallback_code(code: str | None) -> str:
    if not code or code == "free":
        return LEGACY_PACKAGE_CODE
    return code if code in PACKAGES else LEGACY_PACKAGE_CODE


def get_package(code: str | None, db: "Session | None" = None) -> PackageDefinition:
    """Resolve a package from managed DB config when available, else code defaults."""
    resolved = _fallback_code(code)
    if db is not None:
        from app.models import PackageConfig

        config = db.get(PackageConfig, resolved)
        if config is not None:
            return PackageDefinition(
                code=config.code,
                name=config.name,
                max_events=None,
                max_media_per_event=config.max_media_per_event,
                max_storage_bytes_per_event=config.max_storage_bytes_per_event,
                max_video_bytes=config.max_video_bytes,
                guest_gallery=config.guest_gallery,
                archive_downloads=config.archive_downloads,
                custom_event_design=config.custom_event_design,
                tier_rank=config.tier_rank,
                payment_required=config.payment_required,
            )
    return PACKAGES[resolved]


def usage_percent(used: int, limit: int | None) -> float | None:
    if limit is None:
        return None
    if limit <= 0:
        return 100.0
    return min(100.0, round((max(0, used) / limit) * 100, 1))


def package_metadata(code: str | None, db: "Session | None" = None) -> dict[str, object]:
    package = get_package(code, db=db)
    return {
        "code": package.code,
        "name": package.name,
        "limits": {
            "max_events": package.max_events,
            "max_media_per_event": package.max_media_per_event,
            "max_storage_bytes_per_event": package.max_storage_bytes_per_event,
            "max_video_bytes": package.max_video_bytes,
        },
        "features": {
            "guest_gallery": package.guest_gallery,
            "archive_downloads": package.archive_downloads,
            "custom_event_design": package.custom_event_design,
        },
        "tier_rank": package.tier_rank,
        "payment_required": package.payment_required,
    }
