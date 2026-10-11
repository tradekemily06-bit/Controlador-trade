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


def test_selected_mode_can_be_changed_without_granting_real_authority():
    store = EcosystemPreferencesStore()
    result = store.update(selected_mode="REAL")
    assert result.selected_mode == "REAL"
    assert result.real_execution_enabled is False


def test_invalid_selected_mode_is_rejected():
    store = EcosystemPreferencesStore()
    try:
        store.update(selected_mode="LIVE")
    except ValueError:
        return
    raise AssertionError("selected_mode inválido deveria ser rejeitado")


def test_watermark_visibility_is_a_persistable_presentation_preference_only():
    store = EcosystemPreferencesStore()
    updated = store.update(watermark_enabled=False)
    assert updated.watermark_enabled is False
    restored = EcosystemPreferencesStore.from_dict({"watermark_enabled": False})
    assert restored.preferences.watermark_enabled is False
    assert restored.preferences.real_execution_enabled is False
    assert restored.preferences.autonomous_operation_enabled is False
