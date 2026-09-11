import pytest

from execution.broker_profiles import (
    IC_MARKETS_MT5_DEMO,
    LHFX_MT5_DEMO,
    BrokerProfile,
    supported_demo_profiles,
)


def test_lhfx_profile_is_demo_only_and_contains_no_credentials():
    assert LHFX_MT5_DEMO.name == "LHFX"
    assert LHFX_MT5_DEMO.platform == "MT5"
    assert LHFX_MT5_DEMO.server == "LHFXSA-Negociação"
    assert LHFX_MT5_DEMO.demo_only is True


def test_ic_markets_profile_remains_available():
    assert IC_MARKETS_MT5_DEMO.server == "ICMarketsSC-Demo"
    assert IC_MARKETS_MT5_DEMO.demo_only is True


def test_supported_profiles_are_demo_only():
    profiles = supported_demo_profiles()
    assert profiles == (IC_MARKETS_MT5_DEMO, LHFX_MT5_DEMO)
    assert all(profile.demo_only for profile in profiles)


def test_profile_rejects_empty_metadata():
    with pytest.raises(ValueError, match="server"):
        BrokerProfile(name="LHFX", platform="MT5", server=" ")
