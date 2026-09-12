from dataclasses import dataclass


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


# Package capabilities are intentionally billing-provider neutral. v0.7 exposes
# these definitions to the product/UI first; upload enforcement is added only
# after the usage experience has been proven in production.
PACKAGES: dict[str, PackageDefinition] = {
    "starter": PackageDefinition(
        code="starter",
        name="Starter",
        max_events=None,
        max_media_per_event=100,
        max_storage_bytes_per_event=1 * GIB,
        max_video_bytes=500 * MIB,
        guest_gallery=False,
        archive_downloads=True,
        custom_event_design=True,
    ),
    "celebration": PackageDefinition(
        code="celebration",
        name="Celebration",
        max_events=None,
        max_media_per_event=500,
        max_storage_bytes_per_event=5 * GIB,
        max_video_bytes=500 * MIB,
        guest_gallery=True,
        archive_downloads=True,
        custom_event_design=True,
    ),
    "premium": PackageDefinition(
        code="premium",
        name="Premium",
        max_events=None,
        max_media_per_event=None,
        max_storage_bytes_per_event=None,
        max_video_bytes=500 * MIB,
        guest_gallery=True,
        archive_downloads=True,
        custom_event_design=True,
    ),
}

DEFAULT_PACKAGE_CODE = "starter"
LEGACY_PACKAGE_CODE = "premium"


def get_package(code: str | None) -> PackageDefinition:
    """Resolve an event package without accidentally restricting legacy data."""
    if not code or code == "free":
        return PACKAGES[LEGACY_PACKAGE_CODE]
    return PACKAGES.get(code, PACKAGES[LEGACY_PACKAGE_CODE])


def usage_percent(used: int, limit: int | None) -> float | None:
    """Return a capped percentage for UI meters; unlimited limits return None."""
    if limit is None:
        return None
    if limit <= 0:
        return 100.0
    return min(100.0, round((max(0, used) / limit) * 100, 1))


def package_metadata(code: str | None) -> dict[str, object]:
    package = get_package(code)
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
    }
