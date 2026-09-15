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


def test_preferences_cannot_disable_critical_notifications():
    store = EcosystemPreferencesStore()
    with pytest.raises(ValueError):
        store.update_notifications(critical_enabled=False)
    assert store.preferences.notifications.critical_enabled is True


def test_psychology_is_enabled_by_default_and_can_be_disabled_independently():
    store = EcosystemPreferencesStore()
    assert store.preferences.psychology_enabled is True
    assert store.preferences.psychology_data_collection_enabled is True

    result = store.update(psychology_enabled=False)
    assert result.psychology_enabled is False
    assert result.psychology_data_collection_enabled is True
    assert result.real_execution_enabled is False


def test_psychology_data_collection_can_be_disabled_without_disabling_core_safety():
    store = EcosystemPreferencesStore()
    result = store.update(psychology_data_collection_enabled=False)
    assert result.psychology_enabled is True
    assert result.psychology_data_collection_enabled is False
    assert result.notifications.critical_enabled is True


def test_psychology_controls_require_boolean_values():
    store = EcosystemPreferencesStore()
    with pytest.raises(ValueError):
        store.update(psychology_enabled="false")
    with pytest.raises(ValueError):
        store.update(psychology_data_collection_enabled=1)
