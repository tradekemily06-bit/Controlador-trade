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


def test_trader_psychology_can_be_manually_enabled_or_disabled():
    store = EcosystemPreferencesStore()
    assert store.preferences.trader_psychology_enabled is True

    disabled = store.update(trader_psychology_enabled=False)
    assert disabled.trader_psychology_enabled is False
    assert disabled.real_execution_enabled is False

    enabled = store.update(trader_psychology_enabled=True)
    assert enabled.trader_psychology_enabled is True


def test_trader_psychology_toggle_requires_boolean():
    store = EcosystemPreferencesStore()
    with pytest.raises(ValueError):
        store.update(trader_psychology_enabled="false")


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


def test_preferences_persist_use_mode_notifications_and_psychology(tmp_path):
    from core.ecosystem_preferences import EcosystemUseMode

    db = tmp_path / "preferences.sqlite3"
    store = EcosystemPreferencesStore(database_path=str(db))
    store.update(use_mode=EcosystemUseMode.STUDY, trader_psychology_enabled=False)
    store.update_notifications(risk_enabled=False, info_enabled=True)

    restored = EcosystemPreferencesStore(database_path=str(db))
    assert restored.preferences.use_mode is EcosystemUseMode.STUDY
    assert restored.preferences.trader_psychology_enabled is False
    assert restored.preferences.notifications.risk_enabled is False
    assert restored.preferences.notifications.info_enabled is True
    assert restored.preferences.notifications.critical_enabled is True


def test_corrupt_preferences_do_not_get_silently_overwritten(tmp_path):
    db = tmp_path / "preferences.sqlite3"
    import sqlite3

    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE preferences (id INTEGER PRIMARY KEY CHECK(id=1), payload TEXT NOT NULL)")
        conn.execute("INSERT INTO preferences(id, payload) VALUES(1, ?)", ("{not-json",))

    store = EcosystemPreferencesStore(database_path=str(db))
    assert store.storage_corrupted is True
    with sqlite3.connect(db) as conn:
        payload = conn.execute("SELECT payload FROM preferences WHERE id=1").fetchone()[0]
    assert payload == "{not-json"


def test_preferences_store_never_persists_execution_authority(tmp_path):
    db = tmp_path / "preferences.sqlite3"
    store = EcosystemPreferencesStore(database_path=str(db))
    restored = EcosystemPreferencesStore(database_path=str(db))
    assert restored.preferences.real_execution_enabled is False
    assert restored.preferences.autonomous_operation_enabled is False
