from app.branding import FONT_MAP, router as branding_router, valid_hex


def test_branding_public_routes_are_registered():
    paths = {route.path for route in branding_router.routes if hasattr(route, "path")}
    assert "/brand.css" in paths
    assert "/brand/logo" in paths
    assert "/brand/favicon" in paths


def test_branding_font_catalog_is_curated():
    assert {"inter", "montserrat", "poppins", "playfair", "cormorant", "libre-baskerville"}.issubset(FONT_MAP)


def test_branding_color_validation_falls_back_safely():
    assert valid_hex("#A47F76", "#000000") == "#a47f76"
    assert valid_hex("red", "#000000") == "#000000"
