from decimal import Decimal

import pytest

from core.ecosystem_media import EcosystemImage, MediaKind
from core.leverage_profiles import LeverageProfile, LeverageProfileStore


def test_profile_is_context_not_permission():
    store = LeverageProfileStore()
    profile = LeverageProfile("p1", "Perfil principal", "USD", Decimal("1000"), Decimal("20"))
    store.put(profile)
    assert store.get("p1") == profile
    assert store.list_active() == (profile,)


def test_profile_rejects_non_finite_risk_budget():
    with pytest.raises(ValueError):
        LeverageProfile("p1", "Perfil", "USD", Decimal("NaN"))


def test_safe_image_metadata_is_accepted():
    image = EcosystemImage("img1", MediaKind.PROFILE, "image/png", 1024, "media/img1.png")
    image.validate()


def test_image_validation_rejects_unsafe_or_oversized_metadata():
    with pytest.raises(ValueError):
        EcosystemImage("img1", MediaKind.PROFILE, "image/svg+xml", 100, "media/a.svg").validate()
    with pytest.raises(ValueError):
        EcosystemImage("img1", MediaKind.PROFILE, "image/png", 6 * 1024 * 1024, "media/a.png").validate()
    with pytest.raises(ValueError):
        EcosystemImage("img1", MediaKind.PROFILE, "image/png", 100, "https://example.com/a.png").validate()
