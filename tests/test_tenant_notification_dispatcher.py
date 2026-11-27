from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path

from core.ecosystem_notifications import EcosystemNotification, NotificationKind, NotificationSeverity
from security.sqlite_tenant_storage import SQLiteTenantStorage
from security.tenant_context import TenantContext
from security.tenant_scoped_ecosystem_state import TenantScopedEcosystemState
from integration.tenant_notification_dispatcher import TenantNotificationDispatcher


class TenantNotificationDispatcherTests(unittest.TestCase):
    def test_dispatch_requires_explicit_recipient_and_does_not_broadcast(self):
        with tempfile.TemporaryDirectory() as directory:
            state = TenantScopedEcosystemState(SQLiteTenantStorage(Path(directory) / "tenant.sqlite3"))
            dispatcher = TenantNotificationDispatcher(state)
            event = EcosystemNotification(
                notification_id="market-eurusd-m5-001",
                kind=NotificationKind.MARKET,
                severity=NotificationSeverity.IMPORTANT,
                title="Mudança de sinal",
                message="Revisão manual necessária.",
            )
            alice = TenantContext("tenant-a", "alice")
            bob = TenantContext("tenant-a", "bob")
            self.assertTrue(dispatcher.publish(alice, event))
            self.assertFalse(dispatcher.publish(alice, event))
            self.assertEqual(len(state.load_notifications(alice)), 1)
            self.assertEqual(state.load_notifications(bob), [])
            self.assertEqual(dispatcher.outbox.status_counts(alice)["PENDING"], 1)
            self.assertEqual(dispatcher.outbox.status_counts(bob)["PENDING"], 0)

    def test_dispatch_rejects_malformed_dataclass_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            state = TenantScopedEcosystemState(SQLiteTenantStorage(Path(directory) / "tenant.sqlite3"))
            dispatcher = TenantNotificationDispatcher(state)
            malformed = EcosystemNotification(
                notification_id="n2",
                kind="NOT_A_KIND",  # type: ignore[arg-type]
                severity=NotificationSeverity.INFO,
                title="Aviso",
                message="Mensagem",
            )
            with self.assertRaises(ValueError):
                dispatcher.publish(TenantContext("tenant-a", "alice"), malformed)

    def test_dispatch_rejects_missing_or_invalid_context_and_event(self):
        with tempfile.TemporaryDirectory() as directory:
            state = TenantScopedEcosystemState(SQLiteTenantStorage(Path(directory) / "tenant.sqlite3"))
            dispatcher = TenantNotificationDispatcher(state)
            event = EcosystemNotification(
                notification_id="n1", kind=NotificationKind.SECURITY,
                severity=NotificationSeverity.CRITICAL, title="Aviso",
                message="Verificar acesso.",
            )
            with self.assertRaises(PermissionError):
                dispatcher.publish(None, event)  # type: ignore[arg-type]
            with self.assertRaises(TypeError):
                dispatcher.publish(TenantContext("t", "s"), {})  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()



class _TenantSink:
    def __init__(self):
        self.deliveries = []

    def deliver(self, idempotency_key, recipient, payload):
        self.deliveries.append((idempotency_key, dict(recipient), dict(payload)))


def test_tenant_outbox_delivers_only_explicit_recipient_and_is_idempotent(tmp_path):
    storage = SQLiteTenantStorage(tmp_path / "tenant.sqlite3")
    state = TenantScopedEcosystemState(storage)
    dispatcher = TenantNotificationDispatcher(state)
    alice = TenantContext("tenant-a", "alice")
    event = EcosystemNotification(
        notification_id="private-alert-001", kind=NotificationKind.MARKET,
        severity=NotificationSeverity.IMPORTANT, title="EURUSD",
        message="Novo sinal disponível",
    )
    assert dispatcher.publish(alice, event) is True
    assert dispatcher.publish(alice, event) is False

    sink = _TenantSink()
    result = dispatcher.outbox.dispatch_due(sink)
    assert result.claimed == 1
    assert result.delivered == 1
    assert sink.deliveries[0][1] == {"tenant_id": "tenant-a", "subject_id": "alice"}
    assert sink.deliveries[0][2]["notification_id"] == "private-alert-001"
    assert dispatcher.outbox.status_counts(alice)["DELIVERED"] == 1
    assert dispatcher.outbox.status_counts(TenantContext("tenant-a", "bob"))["DELIVERED"] == 0


def test_tenant_outbox_retries_and_dead_letters_without_cross_owner_visibility(tmp_path):
    storage = SQLiteTenantStorage(tmp_path / "tenant.sqlite3")
    state = TenantScopedEcosystemState(storage)
    dispatcher = TenantNotificationDispatcher(state)
    alice = TenantContext("tenant-a", "alice")
    bob = TenantContext("tenant-a", "bob")
    event = EcosystemNotification(
        notification_id="retry-alert", kind=NotificationKind.SECURITY,
        severity=NotificationSeverity.CRITICAL, title="Falha",
        message="Conexão interrompida",
    )
    dispatcher.publish(alice, event)
    now = time.time()
    item = dispatcher.outbox.claim_due(now=now, lease_seconds=10)[0]
    assert dispatcher.outbox.mark_failed(item, "Bearer secret-token", now=now) == "PENDING"
    assert dispatcher.outbox.status_counts(alice)["PENDING"] == 1
    assert dispatcher.outbox.status_counts(bob)["PENDING"] == 0
    with storage._connect() as db:
        row = db.execute(
            "SELECT last_error FROM tenant_notification_outbox WHERE tenant_id=? AND subject_id=?",
            ("tenant-a", "alice"),
        ).fetchone()
    assert "secret-token" not in row[0]



def test_tenant_outbox_does_not_acknowledge_delivery_after_lease_expiry(tmp_path):
    storage = SQLiteTenantStorage(tmp_path / "tenant.sqlite3")
    dispatcher = TenantNotificationDispatcher(TenantScopedEcosystemState(storage))
    owner = TenantContext("tenant-a", "alice")
    event = EcosystemNotification(
        notification_id="slow-delivery", kind=NotificationKind.MARKET,
        severity=NotificationSeverity.INFO, title="EURUSD", message="Ciclo",
    )
    dispatcher.publish(owner, event)

    class _SlowSink:
        def deliver(self, idempotency_key, recipient, payload):
            time.sleep(0.03)

    result = dispatcher.outbox.dispatch_due(_SlowSink(), lease_seconds=0.01)
    assert result.claimed == 1
    assert result.delivered == 0
    assert dispatcher.outbox.status_counts(owner)["IN_FLIGHT"] == 1



def test_tenant_outbox_remains_idempotent_after_inbox_retention_evicts_old_event(tmp_path):
    storage = SQLiteTenantStorage(tmp_path / "tenant.sqlite3")
    dispatcher = TenantNotificationDispatcher(TenantScopedEcosystemState(storage))
    owner = TenantContext("tenant-a", "alice")
    first = {"notification_id": "old-event", "title": "old", "message": "old"}
    assert dispatcher.outbox.publish(owner, first, inbox_limit=2) is True
    assert dispatcher.outbox.publish(owner, {"notification_id": "event-2"}, inbox_limit=2) is True
    assert dispatcher.outbox.publish(owner, {"notification_id": "event-3"}, inbox_limit=2) is True
    assert dispatcher.outbox.publish(owner, first, inbox_limit=2) is False
    assert dispatcher.outbox.status_counts(owner)["PENDING"] == 3



def test_tenant_outbox_dead_letters_after_retry_budget(tmp_path):
    from core.tenant_notification_outbox import TenantNotificationOutbox

    storage = SQLiteTenantStorage(tmp_path / "tenant.sqlite3")
    outbox = TenantNotificationOutbox(storage, max_attempts=2, base_backoff_seconds=5)
    owner = TenantContext("tenant-a", "alice")
    assert outbox.publish(owner, {"notification_id": "dead-event"}, now=100) is True
    first = outbox.claim_due(now=100, lease_seconds=20)[0]
    assert outbox.mark_failed(first, "temporary failure", now=100) == "PENDING"
    second = outbox.claim_due(now=105, lease_seconds=20)[0]
    assert second.attempts == 2
    assert outbox.mark_failed(second, "permanent failure", now=105) == "DEAD"
    assert outbox.status_counts(owner)["DEAD"] == 1
