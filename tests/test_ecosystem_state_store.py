from pathlib import Path

from core.ecosystem_notifications import EcosystemNotificationCenter, NotificationKind, NotificationSeverity
from core.ecosystem_preferences import EcosystemPreferencesStore
from core.ecosystem_state_store import EcosystemStateStore


def test_preferences_survive_restart(tmp_path: Path):
    db = tmp_path / "state.sqlite"
    first = EcosystemStateStore(db)
    preferences = EcosystemPreferencesStore()
    preferences.update(default_symbol="GBPUSD", default_timeframe="5m")
    first.save_preferences(preferences.preferences)

    second = EcosystemStateStore(db)
    restored = EcosystemPreferencesStore.from_dict(second.load_preferences())
    assert restored.preferences.default_symbol == "GBPUSD"
    assert restored.preferences.default_timeframe == "5m"
    assert restored.preferences.real_execution_enabled is False
    assert restored.preferences.autonomous_operation_enabled is False


def test_selected_mode_survives_restart_without_granting_real_authority(tmp_path: Path):
    db = tmp_path / "state.sqlite"
    first = EcosystemStateStore(db)
    preferences = EcosystemPreferencesStore()
    preferences.update(selected_mode="REAL")
    first.save_preferences(preferences.preferences)

    second = EcosystemStateStore(db)
    restored = EcosystemPreferencesStore.from_dict(second.load_preferences())
    assert restored.preferences.selected_mode == "REAL"
    assert restored.preferences.real_execution_enabled is False


def test_notifications_survive_restart(tmp_path: Path):
    db = tmp_path / "state.sqlite"
    first = EcosystemStateStore(db)
    center = EcosystemNotificationCenter()
    center.publish(
        __import__("core.ecosystem_notifications", fromlist=["EcosystemNotification"]).EcosystemNotification(
            "n1",
            NotificationKind.CONNECTION,
            NotificationSeverity.IMPORTANT,
            "Conexão",
            "MT5 DEMO conectado.",
        )
    )
    first.save_notifications(
        [
            {
                "notification_id": item.notification_id,
                "kind": item.kind.value,
                "severity": item.severity.value,
                "title": item.title,
                "message": item.message,
                "requires_attention": item.requires_attention,
                "blocking": item.blocking,
            }
            for item in center.all()
        ]
    )

    second = EcosystemStateStore(db)
    restored = EcosystemNotificationCenter()
    restored.restore(second.load_notifications())
    assert len(restored.all()) == 1
    assert restored.all()[0].notification_id == "n1"


def test_state_store_is_not_an_execution_authority(tmp_path: Path):
    db = EcosystemStateStore(tmp_path / "state.sqlite")
    db.save("preferences", {"real_execution_enabled": True, "autonomous_operation_enabled": True})
    restored = EcosystemPreferencesStore.from_dict(db.load_preferences())
    assert restored.preferences.real_execution_enabled is False
    assert restored.preferences.autonomous_operation_enabled is False
