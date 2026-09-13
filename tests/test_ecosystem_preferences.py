import pytest

from core.ecosystem_preferences import (
    CandleColorMode,
    CandleStyle,
    EcosystemPreferencesStore,
)


def test_preferences_support_candle_appearance_changes_without_execution_authority():
    store = EcosystemPreferencesStore()
    result = store.update_candle(
        style=CandleStyle.HOLLOW,
        color_mode=CandleColorMode.CUSTOM,
        bullish_color="#00ff00",
        bearish_color="#ff00ff",
    )
    assert result.candle.style is CandleStyle.HOLLOW
    assert result.candle.color_mode is CandleColorMode.CUSTOM
    assert result.real_execution_enabled is False
    assert result.autonomous_operation_enabled is False


def test_preferences_cannot_enable_real_or_autonomous_operation():
    store = EcosystemPreferencesStore()
    with pytest.raises(ValueError):
        store.update(real_execution_enabled=True)
    with pytest.raises(ValueError):
        store.update(autonomous_operation_enabled=True)
