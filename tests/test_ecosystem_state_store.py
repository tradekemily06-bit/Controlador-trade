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


def test_corrupt_notification_json_does_not_prevent_state_store_startup(tmp_path: Path):
    db = EcosystemStateStore(tmp_path / "state.sqlite")
    with db._connect() as connection:
        connection.execute(
            "INSERT INTO ecosystem_state(key, value_json) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json",
            ("notifications", "{broken-json"),
        )

    restored = db.load_notifications()

    assert restored == []
    assert db.notifications_load_error == "invalid_json"


def test_corrupt_notification_history_is_not_overwritten_by_routine_save(tmp_path: Path):
    import pytest

    db = EcosystemStateStore(tmp_path / "state.sqlite")
    with db._connect() as connection:
        connection.execute(
            "INSERT INTO ecosystem_state(key, value_json) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json",
            ("notifications", "{broken-json"),
        )

    assert db.load_notifications() == []
    with pytest.raises(RuntimeError, match="explicit recovery"):
        db.save_notifications([{"notification_id": "new-event"}])

    with db._connect() as connection:
        stored = connection.execute(
            "SELECT value_json FROM ecosystem_state WHERE key = ?",
            ("notifications",),
        ).fetchone()[0]
    assert stored == "{broken-json"


def test_notification_store_read_error_is_reported_without_crashing(tmp_path: Path, monkeypatch):
    import sqlite3

    db = EcosystemStateStore(tmp_path / "state.sqlite")

    def fail_read(_key):
        raise sqlite3.OperationalError("private database path and SQL details")

    monkeypatch.setattr(db, "load", fail_read)

    assert db.load_notifications() == []
    assert db.notifications_load_error == "read_failed"


def test_generic_state_save_cannot_bypass_notification_history_guard(tmp_path):
    import sqlite3

    import pytest

    path = tmp_path / "notification-write-guard.sqlite3"
    store = EcosystemStateStore(path)
    with sqlite3.connect(path) as db:
        db.execute(
            "INSERT INTO ecosystem_state(key, value_json) VALUES (?, ?)",
            ("notifications", "{broken-json"),
        )

    assert store.load_notifications() == []
    with pytest.raises(ValueError, match="save_notifications"):
        store.save("notifications", [{"notification_id": "replacement"}])

    with sqlite3.connect(path) as db:
        raw = db.execute(
            "SELECT value_json FROM ecosystem_state WHERE key = ?",
            ("notifications",),
        ).fetchone()[0]
    assert raw == "{broken-json"


def test_notification_history_uses_only_dedicated_writer(tmp_path):
    import pytest

    store = EcosystemStateStore(tmp_path / "notification-dedicated-writer.sqlite3")
    with pytest.raises(ValueError, match="save_notifications"):
        store.save("notifications", [{"notification_id": "n1"}])

    store.save_notifications([{"notification_id": "n1"}])
    assert store.load_notifications() == [{"notification_id": "n1"}]


def test_notification_quarantine_requires_explicit_confirmation(tmp_path):
    import sqlite3

    import pytest

    path = tmp_path / "notification-quarantine-confirmation.sqlite3"
    store = EcosystemStateStore(path)
    raw = "{broken-json"
    with sqlite3.connect(path) as db:
        db.execute(
            "INSERT INTO ecosystem_state(key, value_json) VALUES (?, ?)",
            ("notifications", raw),
        )

    store.load_notifications()
    with pytest.raises(ValueError, match="confirmação explícita"):
        store.archive_notifications_for_recovery(confirmed=False)

    with sqlite3.connect(path) as db:
        assert db.execute(
            "SELECT COUNT(*) FROM notification_history_quarantine"
        ).fetchone()[0] == 0
        assert db.execute(
            "SELECT value_json FROM ecosystem_state WHERE key = ?",
            ("notifications",),
        ).fetchone()[0] == raw


def test_notification_quarantine_preserves_exact_payload_without_repairing(tmp_path):
    import hashlib
    import sqlite3

    path = tmp_path / "notification-quarantine-preserve.sqlite3"
    store = EcosystemStateStore(path)
    raw = '[{"notification_id":"kept","kind":"UNKNOWN","severity":"IMPORTANT","title":"t","message":"m"}]'
    with sqlite3.connect(path) as db:
        db.execute(
            "INSERT INTO ecosystem_state(key, value_json) VALUES (?, ?)",
            ("notifications", raw),
        )

    store.load_notifications()
    # The notification center detects invalid enum/field values during restore.
    store.mark_notifications_unavailable("invalid_records")
    archive = store.archive_notifications_for_recovery(confirmed=True)

    assert archive["corruption_category"] == "invalid_records"
    assert archive["payload_sha256"] == hashlib.sha256(raw.encode("utf-8")).hexdigest()
    assert store.notifications_load_error == "invalid_records"

    with sqlite3.connect(path) as db:
        original = db.execute(
            "SELECT value_json FROM ecosystem_state WHERE key = ?",
            ("notifications",),
        ).fetchone()[0]
        archived = db.execute(
            "SELECT raw_payload, payload_sha256, corruption_category "
            "FROM notification_history_quarantine WHERE archive_id = ?",
            (archive["archive_id"],),
        ).fetchone()

    assert original == raw
    assert archived == (raw, archive["payload_sha256"], "invalid_records")


def test_notification_quarantine_can_preserve_payload_after_transient_read_failure(tmp_path, monkeypatch):
    import sqlite3

    path = tmp_path / "notification-quarantine-read-failure.sqlite3"
    store = EcosystemStateStore(path)
    raw = '[{"notification_id":"original"}]'
    with sqlite3.connect(path) as db:
        db.execute(
            "INSERT INTO ecosystem_state(key, value_json) VALUES (?, ?)",
            ("notifications", raw),
        )

    def fail_read(_key):
        raise sqlite3.OperationalError("temporary read failure")

    monkeypatch.setattr(store, "load", fail_read)
    assert store.load_notifications() == []
    assert store.notifications_load_error == "read_failed"

    archive = store.archive_notifications_for_recovery(confirmed=True)
    assert archive["corruption_category"] == "read_failed"

    with sqlite3.connect(path) as db:
        original = db.execute(
            "SELECT value_json FROM ecosystem_state WHERE key = ?",
            ("notifications",),
        ).fetchone()[0]
        archived = db.execute(
            "SELECT raw_payload FROM notification_history_quarantine WHERE archive_id = ?",
            (archive["archive_id"],),
        ).fetchone()[0]

    assert original == raw
    assert archived == raw
    assert store.notifications_load_error == "read_failed"


def test_notification_quarantine_preserves_binary_corrupt_payload(tmp_path):
    import hashlib
    import sqlite3

    path = tmp_path / "notification-quarantine-binary.sqlite3"
    store = EcosystemStateStore(path)
    raw = b"\\x00\\xffnot-json"
    with sqlite3.connect(path) as db:
        db.execute(
            "INSERT INTO ecosystem_state(key, value_json) VALUES (?, ?)",
            ("notifications", sqlite3.Binary(raw)),
        )

    assert store.load_notifications() == []
    assert store.notifications_load_error == "read_failed" or store.notifications_load_error == "invalid_json"
    archive = store.archive_notifications_for_recovery(confirmed=True)

    with sqlite3.connect(path) as db:
        original = db.execute(
            "SELECT value_json FROM ecosystem_state WHERE key = ?",
            ("notifications",),
        ).fetchone()[0]
        archived = db.execute(
            "SELECT raw_payload FROM notification_history_quarantine WHERE archive_id = ?",
            (archive["archive_id"],),
        ).fetchone()[0]

    assert isinstance(original, bytes)
    assert original == raw
    assert archived == raw
    assert archive["payload_sha256"] == hashlib.sha256(raw).hexdigest()


def test_notification_quarantine_restore_requires_confirmation_and_keeps_archive(tmp_path):
    import sqlite3
    import pytest

    path = tmp_path / "notification-quarantine-restore.sqlite3"
    store = EcosystemStateStore(path)
    raw = '[{"notification_id":"n1","kind":"SECURITY","severity":"CRITICAL","title":"Alerta","message":"Verificar","requires_attention":true,"blocking":true}]'
    with sqlite3.connect(path) as db:
        db.execute(
            "INSERT INTO ecosystem_state(key, value_json) VALUES (?, ?)",
            ("notifications", raw),
        )

    assert store.load_notifications() == [
        {
            "notification_id": "n1",
            "kind": "SECURITY",
            "severity": "CRITICAL",
            "title": "Alerta",
            "message": "Verificar",
            "requires_attention": True,
            "blocking": True,
        }
    ]
    store.mark_notifications_unavailable("invalid_records")
    archive = store.archive_notifications_for_recovery(confirmed=True)

    with pytest.raises(ValueError, match="confirmação explícita"):
        store.restore_notifications_from_quarantine(archive["archive_id"], confirmed=False)

    result = store.restore_notifications_from_quarantine(
        archive["archive_id"], confirmed=True
    )
    assert result == {
        "archive_id": archive["archive_id"],
        "restored_count": 1,
        "integrity_verified": True,
        "archive_preserved": True,
    }
    assert store.notifications_load_error is None
    assert store.load_notifications()[0]["notification_id"] == "n1"

    with sqlite3.connect(path) as db:
        archived = db.execute(
            "SELECT raw_payload, payload_sha256 FROM notification_history_quarantine WHERE archive_id = ?",
            (archive["archive_id"],),
        ).fetchone()
    assert archived == (raw, archive["payload_sha256"])


def test_notification_quarantine_restore_rejects_invalid_records_without_partial_restore(tmp_path):
    import sqlite3
    import pytest
    from core.ecosystem_state_store import NotificationHistoryUnavailableError

    path = tmp_path / "notification-quarantine-invalid.sqlite3"
    store = EcosystemStateStore(path)
    raw = '[{"notification_id":"valid","kind":"SECURITY","severity":"CRITICAL","title":"A","message":"B"},{"notification_id":"bad","kind":"UNKNOWN","severity":"CRITICAL","title":"C","message":"D"}]'
    with sqlite3.connect(path) as db:
        db.execute(
            "INSERT INTO ecosystem_state(key, value_json) VALUES (?, ?)",
            ("notifications", raw),
        )

    store.load_notifications()
    store.mark_notifications_unavailable("invalid_records")
    archive = store.archive_notifications_for_recovery(confirmed=True)
    with pytest.raises(NotificationHistoryUnavailableError, match="inválidas"):
        store.restore_notifications_from_quarantine(archive["archive_id"], confirmed=True)

    with sqlite3.connect(path) as db:
        assert db.execute(
            "SELECT value_json FROM ecosystem_state WHERE key = ?",
            ("notifications",),
        ).fetchone()[0] == raw


def test_notification_quarantine_restore_rejects_changed_original(tmp_path):
    import sqlite3
    import pytest
    from core.ecosystem_state_store import NotificationHistoryUnavailableError

    path = tmp_path / "notification-quarantine-changed.sqlite3"
    store = EcosystemStateStore(path)
    raw = '[{"notification_id":"n1","kind":"SECURITY","severity":"CRITICAL","title":"A","message":"B"}]'
    with sqlite3.connect(path) as db:
        db.execute(
            "INSERT INTO ecosystem_state(key, value_json) VALUES (?, ?)",
            ("notifications", raw),
        )

    store.load_notifications()
    store.mark_notifications_unavailable("invalid_records")
    archive = store.archive_notifications_for_recovery(confirmed=True)
    with sqlite3.connect(path) as db:
        db.execute(
            "UPDATE ecosystem_state SET value_json = ? WHERE key = ?",
            ('[{"notification_id":"new","kind":"SECURITY","severity":"CRITICAL","title":"X","message":"Y"}]', "notifications"),
        )

    with pytest.raises(NotificationHistoryUnavailableError, match="mudou desde o arquivamento"):
        store.restore_notifications_from_quarantine(archive["archive_id"], confirmed=True)


def test_notification_quarantine_inspection_detects_archive_tampering(tmp_path):
    import sqlite3
    import pytest
    from core.ecosystem_state_store import NotificationHistoryUnavailableError

    path = tmp_path / "notification-quarantine-tampered.sqlite3"
    store = EcosystemStateStore(path)
    raw = '[{"notification_id":"n1","kind":"SECURITY","severity":"CRITICAL","title":"A","message":"B"}]'
    with sqlite3.connect(path) as db:
        db.execute(
            "INSERT INTO ecosystem_state(key, value_json) VALUES (?, ?)",
            ("notifications", raw),
        )

    store.load_notifications()
    store.mark_notifications_unavailable("invalid_records")
    archive = store.archive_notifications_for_recovery(confirmed=True)
    with sqlite3.connect(path) as db:
        db.execute(
            "UPDATE notification_history_quarantine SET raw_payload = ? WHERE archive_id = ?",
            (raw + " ", archive["archive_id"]),
        )

    with pytest.raises(NotificationHistoryUnavailableError, match="integridade"):
        store.inspect_notification_quarantine(archive["archive_id"])



def test_notification_quarantine_restore_verifies_archive_without_separate_inspection(tmp_path, monkeypatch):
    import sqlite3

    path = tmp_path / "notification-quarantine-atomic-restore.sqlite3"
    store = EcosystemStateStore(path)
    raw = '[{"notification_id":"n1","kind":"SECURITY","severity":"CRITICAL","title":"A","message":"B","requires_attention":false,"blocking":false}]'
    with sqlite3.connect(path) as db:
        db.execute(
            "INSERT INTO ecosystem_state(key, value_json) VALUES (?, ?)",
            ("notifications", raw),
        )

    store.load_notifications()
    store.mark_notifications_unavailable("invalid_records")
    archive = store.archive_notifications_for_recovery(confirmed=True)

    def separate_inspection_must_not_be_used(_archive_id):
        raise AssertionError("restore must verify archive inside its own SQLite transaction")

    monkeypatch.setattr(
        store, "inspect_notification_quarantine", separate_inspection_must_not_be_used
    )
    restored = store.restore_notifications_from_quarantine(
        archive["archive_id"], confirmed=True
    )

    assert restored["integrity_verified"] is True
    assert restored["archive_preserved"] is True
    assert restored["restored_count"] == 1
    assert store.notifications_load_error is None
    with sqlite3.connect(path) as db:
        current = db.execute(
            "SELECT value_json FROM ecosystem_state WHERE key = ?",
            ("notifications",),
        ).fetchone()[0]
        archived = db.execute(
            "SELECT raw_payload FROM notification_history_quarantine WHERE archive_id = ?",
            (archive["archive_id"],),
        ).fetchone()[0]
    assert current == raw
    assert archived == raw


def test_notification_corruption_flag_and_writer_are_serialized(tmp_path, monkeypatch):
    import json
    import sqlite3
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    from core.ecosystem_state_store import NotificationHistoryUnavailableError

    path = tmp_path / "notification-corruption-lock.sqlite3"
    store = EcosystemStateStore(path)
    store.mark_notifications_unavailable("invalid_records")
    read_started = Event()
    allow_read_to_finish = Event()
    save_attempted = Event()
    save_finished = Event()

    def blocked_corrupt_read(_key):
        read_started.set()
        assert allow_read_to_finish.wait(timeout=5)
        raise json.JSONDecodeError("corrupt", "{", 0)

    def concurrent_save():
        save_attempted.set()
        try:
            store.save_notifications([])
        finally:
            save_finished.set()

    monkeypatch.setattr(store, "load", blocked_corrupt_read)

    with ThreadPoolExecutor(max_workers=2) as pool:
        load_future = pool.submit(store.load_notifications)
        assert read_started.wait(timeout=5)
        save_future = pool.submit(concurrent_save)
        assert save_attempted.wait(timeout=5)
        assert not save_finished.wait(timeout=0.05)
        allow_read_to_finish.set()
        assert load_future.result(timeout=5) == []
        try:
            save_future.result(timeout=5)
        except NotificationHistoryUnavailableError:
            pass
        else:
            raise AssertionError("writer must not pass while corruption is being detected")

    with sqlite3.connect(path) as db:
        assert db.execute(
            "SELECT value_json FROM ecosystem_state WHERE key = ?",
            ("notifications",),
        ).fetchone() is None
    assert store.notifications_load_error == "invalid_json"
