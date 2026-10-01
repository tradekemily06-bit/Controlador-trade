from __future__ import annotations

import json

from core.ecosystem_notifications import EcosystemNotification, EcosystemNotificationCenter, NotificationKind, NotificationSeverity
from core.ecosystem_preferences import EcosystemPreferencesStore
from integration.ecosystem_service import EcosystemService


def test_preferences_survive_restart(tmp_path):
    path = tmp_path / "preferences.json"
    first = EcosystemPreferencesStore(path=path)
    first.update(default_symbol="GBPUSD", default_timeframe="1m")
    second = EcosystemPreferencesStore(path=path)
    assert second.preferences.default_symbol == "GBPUSD"
    assert second.preferences.default_timeframe == "1m"
    assert second.preferences.real_execution_enabled is False
    assert second.preferences.autonomous_operation_enabled is False


def test_notification_history_survives_restart(tmp_path):
    path = tmp_path / "notifications.json"
    first = EcosystemNotificationCenter(path=path)
    first.publish(EcosystemNotification("n1", NotificationKind.RISK, NotificationSeverity.IMPORTANT, "Risk", "Persisted"))
    second = EcosystemNotificationCenter(path=path)
    assert [item.notification_id for item in second.all()] == ["n1"]


def test_learning_state_survives_restart_without_operation_authority(tmp_path):
    first = EcosystemService(runtime_dir=tmp_path)
    first.add_learning_resource({"resource_id": "r1", "title": "Study", "content_type": "NOTE"})
    first.add_learning_activity({"activity_id": "a1", "prompt": "Explain", "expected_concepts": ["risk"]})
    first.add_learning_attempt({"activity_id": "a1", "answer": "risk", "correct": True})
    second = EcosystemService(runtime_dir=tmp_path)
    assert "r1" in second.learning_resources
    assert "a1" in second.learning_activities
    assert second.learning_attempts[0].correct is True
    assert second.learning_summary()["learning_authorizes_trading"] is False


def test_persistence_files_are_json_objects_or_lists(tmp_path):
    service = EcosystemService(runtime_dir=tmp_path)
    service.add_learning_resource({"resource_id": "r1", "title": "Study", "content_type": "NOTE"})
    payload = json.loads((tmp_path / "learning-state.json").read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
