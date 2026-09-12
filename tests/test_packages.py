from app.services.packages import (
    DEFAULT_PACKAGE_CODE,
    PACKAGES,
    get_package,
    package_metadata,
    usage_percent,
)


def test_named_packages_are_available():
    assert set(PACKAGES) == {"starter", "celebration", "premium"}
    assert DEFAULT_PACKAGE_CODE == "starter"
    assert PACKAGES["starter"].max_media_per_event == 100
    assert PACKAGES["celebration"].max_media_per_event == 500
    assert PACKAGES["premium"].max_media_per_event is None
    assert PACKAGES["premium"].max_storage_bytes_per_event is None


def test_legacy_and_unknown_packages_fall_back_to_premium():
    assert get_package("free").code == "premium"
    assert get_package(None).code == "premium"
    assert get_package("something-old").code == "premium"


def test_package_metadata_is_ui_ready():
    metadata = package_metadata("celebration")
    assert metadata["code"] == "celebration"
    assert metadata["name"] == "Celebration"
    assert metadata["limits"]["max_media_per_event"] == 500
    assert metadata["features"]["guest_gallery"] is True
    assert metadata["features"]["custom_event_design"] is True


def test_usage_percent_supports_unlimited_limits():
    assert usage_percent(50, 100) == 50.0
    assert usage_percent(150, 100) == 100.0
    assert usage_percent(10, None) is None
