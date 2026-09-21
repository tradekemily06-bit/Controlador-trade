from pathlib import Path

from core.ecosystem_notifications import EcosystemNotification, EcosystemNotificationCenter, NotificationKind, NotificationSeverity
from core.learning_content import LearningObservation
from core.scoped_learning_state import ScopedLearningState
from storage.scoped_state_store import SQLiteScopedStateStore


def test_scoped_store_update_serializes_read_modify_write(tmp_path: Path):
    store_a = SQLiteScopedStateStore(tmp_path / "state.db")
    store_b = SQLiteScopedStateStore(tmp_path / "state.db")
    store_a.put(tenant_id="tenant", subject_id="subject", namespace="counter", payload={"items": ["a"]})

    store_a.update(
        tenant_id="tenant",
        subject_id="subject",
        namespace="counter",
        updater=lambda value: {"items": list(value["items"]) + ["b"]},
    )
    store_b.update(
        tenant_id="tenant",
        subject_id="subject",
        namespace="counter",
        updater=lambda value: {"items": list(value["items"]) + ["c"]},
    )

    assert store_a.get(tenant_id="tenant", subject_id="subject", namespace="counter") == {"items": ["a", "b", "c"]}


def test_notifications_do_not_lose_stale_worker_append(tmp_path: Path):
    db = tmp_path / "state.db"
    store_a = SQLiteScopedStateStore(db)
    store_b = SQLiteScopedStateStore(db)
    center_a = EcosystemNotificationCenter(state_store=store_a, require_durable=True)
    center_b = EcosystemNotificationCenter(state_store=store_b, require_durable=True)

    center_a.publish_global(EcosystemNotification("a", NotificationKind.SYSTEM_UPDATE, NotificationSeverity.IMPORTANT, "A", "first"))
    center_b.publish_global(EcosystemNotification("b", NotificationKind.SYSTEM_UPDATE, NotificationSeverity.IMPORTANT, "B", "second"))

    assert {item.notification_id for item in center_a.all()} == {"a", "b"}
    assert {item.notification_id for item in center_b.all()} == {"a", "b"}


def test_learning_persist_keeps_additive_updates_from_stale_workers(tmp_path: Path):
    db = tmp_path / "state.db"
    store_a = SQLiteScopedStateStore(db)
    store_b = SQLiteScopedStateStore(db)
    learning_a = ScopedLearningState(state_store=store_a, require_durable=True)
    learning_b = ScopedLearningState(state_store=store_b, require_durable=True)

    scope_a = learning_a.get(tenant_id="tenant", subject_id="subject")
    scope_b = learning_b.get(tenant_id="tenant", subject_id="subject")
    scope_a.observations.append(LearningObservation("r1", "observation A"))
    scope_b.observations.append(LearningObservation("r2", "observation B"))

    learning_a.persist(tenant_id="tenant", subject_id="subject")
    learning_b.persist(tenant_id="tenant", subject_id="subject")

    final_scope = learning_a.get(tenant_id="tenant", subject_id="subject")
    assert {item.statement for item in final_scope.observations} == {"observation A", "observation B"}


def test_learning_source_flags_are_monotonic_under_stale_updates(tmp_path: Path):
    db = tmp_path / "state.db"
    store_a = SQLiteScopedStateStore(db)
    store_b = SQLiteScopedStateStore(db)
    learning_a = ScopedLearningState(state_store=store_a, require_durable=True)
    learning_b = ScopedLearningState(state_store=store_b, require_durable=True)

    source_a = learning_a.get(tenant_id="tenant", subject_id="subject")
    source_b = learning_b.get(tenant_id="tenant", subject_id="subject")

    from core.p128_learning_source_gate import LearningSource, LearningSourceStatus, LearningSourceType

    source = LearningSource("s1", LearningSourceType.LINK, "https://example.com", LearningSourceStatus.QUARANTINED)
    source_a.sources[source.source_id] = source
    source_b.sources[source.source_id] = source

    source_a.sources["s1"] = LearningSource("s1", LearningSourceType.LINK, "https://example.com", LearningSourceStatus.QUARANTINED, content_verified=True)
    source_b.sources["s1"] = LearningSource("s1", LearningSourceType.LINK, "https://example.com", LearningSourceStatus.QUARANTINED, security_checked=True)

    learning_a.persist(tenant_id="tenant", subject_id="subject")
    learning_b.persist(tenant_id="tenant", subject_id="subject")

    final = learning_a.get(tenant_id="tenant", subject_id="subject").sources["s1"]
    assert final.content_verified is True
    assert final.security_checked is True


def test_preferences_do_not_lose_stale_worker_updates(tmp_path: Path):
    from core.ecosystem_preferences import EcosystemPreferencesStore

    db = tmp_path / "state.db"
    store_a = SQLiteScopedStateStore(db)
    store_b = SQLiteScopedStateStore(db)
    prefs_a = EcosystemPreferencesStore(state_store=store_a)
    prefs_b = EcosystemPreferencesStore(state_store=store_b)

    from security.http_identity import TrustedHttpIdentity, _current_identity
    token = _current_identity.set(TrustedHttpIdentity("subject", "tenant", "user"))
    try:
        prefs_a.update(default_timeframe="1m")
        prefs_b.update(default_symbol="GBPUSD")
        final = prefs_a.preferences
    finally:
        _current_identity.reset(token)

    assert final.default_timeframe == "1m"
    assert final.default_symbol == "GBPUSD"
