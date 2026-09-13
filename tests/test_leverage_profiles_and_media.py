import pytest
from decimal import Decimal

from core.ecosystem_media import EcosystemImage, MediaKind
from core.leverage_profiles import LeverageProfile, LeverageProfileStore


def test_profiles_are_user_defined_and_do_not_authorize():
    store = LeverageProfileStore()
    profile = LeverageProfile("p1", "Nome definido pelo usuário", "BRL", Decimal("1000"), Decimal("100"))
    store.put(profile)
    assert store.get("p1") == profile
    assert store.list_active() == (profile,)


def test_image_metadata_accepts_safe_supported_type():
    image = EcosystemImage("img1", MediaKind.PROFILE, "image/png", 1024, "media/img1.png")
    image.validate()


@pytest.mark.parametrize("mime", ["image/svg+xml", "application/pdf", "text/html"])
def test_unsupported_image_types_are_rejected(mime):
    image = EcosystemImage("img1", MediaKind.LOGO, mime, 1024, "media/img1")
    with pytest.raises(ValueError, match="unsupported_image_type"):
        image.validate()


def test_remote_or_data_reference_is_rejected():
    image = EcosystemImage("img1", MediaKind.BACKGROUND, "image/webp", 1024, "https://example.invalid/x.webp")
    with pytest.raises(ValueError, match="unsafe_storage_reference"):
        image.validate()


def test_image_size_is_bounded():
    image = EcosystemImage("img1", MediaKind.PROFILE, "image/jpeg", 5 * 1024 * 1024 + 1, "media/img1.jpg")
    with pytest.raises(ValueError, match="image_size_out_of_bounds"):
        image.validate()
