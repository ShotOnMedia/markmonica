from dataclasses import dataclass


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


# Product capabilities live here rather than in payment-provider code. Values are
# intentionally conservative placeholders for v0.5 and can be changed before
# paid packages are exposed to customers.
PACKAGES: dict[str, PackageDefinition] = {
    "free": PackageDefinition(
        code="free",
        name="Free",
        max_events=3,
        max_media_per_event=250,
        max_storage_bytes_per_event=5 * 1024**3,
        max_video_bytes=500 * 1024**2,
        guest_gallery=True,
        archive_downloads=True,
    ),
}

DEFAULT_PACKAGE_CODE = "free"


def get_package(code: str | None) -> PackageDefinition:
    return PACKAGES.get(code or DEFAULT_PACKAGE_CODE, PACKAGES[DEFAULT_PACKAGE_CODE])


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
        },
    }
