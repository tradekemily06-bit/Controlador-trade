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


def test_preferences_persist_across_store_instances(tmp_path):
    path = tmp_path / "ecosystem-preferences.json"
    first = EcosystemPreferencesStore(path=path)
    first.update(default_symbol="GBPUSD", default_timeframe="1m", require_closed_candle=False)

    second = EcosystemPreferencesStore(path=path)
    assert second.preferences.default_symbol == "GBPUSD"
    assert second.preferences.default_timeframe == "1m"
    assert second.preferences.require_closed_candle is False
    assert second.preferences.real_execution_enabled is False
    assert second.preferences.autonomous_operation_enabled is False


def test_corrupt_persisted_preferences_fail_safe_to_defaults(tmp_path):
    path = tmp_path / "ecosystem-preferences.json"
    path.write_text("{not-json", encoding="utf-8")
    store = EcosystemPreferencesStore(path=path)
    assert store.preferences.default_symbol == "EURUSD"
    assert store.preferences.default_timeframe == "5m"
    assert store.preferences.real_execution_enabled is False
