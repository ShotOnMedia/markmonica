from fastapi import HTTPException
import pytest

from app.services.package_enforcement import require_feature
from app.services.packages import PACKAGES


def test_starter_disables_guest_gallery():
    with pytest.raises(HTTPException) as exc:
        require_feature(PACKAGES["starter"], "guest_gallery", "Guest gallery unavailable")
    assert exc.value.status_code == 403


def test_celebration_allows_guest_gallery():
    require_feature(PACKAGES["celebration"], "guest_gallery", "Guest gallery unavailable")


def test_premium_remains_unlimited_for_media_and_storage():
    premium = PACKAGES["premium"]
    assert premium.max_media_per_event is None
    assert premium.max_storage_bytes_per_event is None


def test_starter_limits_are_enforceable():
    starter = PACKAGES["starter"]
    assert starter.max_media_per_event == 100
    assert starter.max_storage_bytes_per_event == 1024**3
    assert starter.max_video_bytes == 500 * 1024**2
