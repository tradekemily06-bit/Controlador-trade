from __future__ import annotations

import time

from core.ecosystem_notifications import EcosystemNotification, NotificationKind, NotificationSeverity
from integration.tenant_notification_dispatcher import TenantNotificationDispatcher
from integration.tenant_notification_outbox_worker import TenantNotificationOutboxWorker
from security.sqlite_tenant_storage import SQLiteTenantStorage
from security.tenant_context import TenantContext
from security.tenant_scoped_ecosystem_state import TenantScopedEcosystemState


class _Sink:
    def __init__(self):
        self.deliveries = []

    def deliver(self, idempotency_key, recipient, payload):
        self.deliveries.append((dict(recipient), dict(payload)))


def test_tenant_notification_worker_starts_delivers_and_stops(tmp_path):
    storage = SQLiteTenantStorage(tmp_path / "tenant.sqlite3")
    dispatcher = TenantNotificationDispatcher(TenantScopedEcosystemState(storage))
    owner = TenantContext("tenant-1", "subject-1")
    event = EcosystemNotification(
        notification_id="worker-event", kind=NotificationKind.MARKET,
        severity=NotificationSeverity.INFO, title="EURUSD", message="Novo ciclo",
    )
    dispatcher.publish(owner, event)
    sink = _Sink()
    worker = TenantNotificationOutboxWorker(
        dispatcher.outbox, sink, poll_interval_seconds=0.01, batch_size=5
    )
    worker.start()
    deadline = time.monotonic() + 2
    while not sink.deliveries and time.monotonic() < deadline:
        time.sleep(0.01)
    status_running = worker.status()
    worker.stop()
    status_stopped = worker.status()
    assert sink.deliveries
    assert sink.deliveries[0][0] == {"tenant_id": "tenant-1", "subject_id": "subject-1"}
    assert status_running["running"] is True
    assert status_stopped["running"] is False
    assert dispatcher.outbox.status_counts(owner)["DELIVERED"] == 1




def test_outbox_failure_diagnostic_never_persists_provider_exception_text(tmp_path):
    storage = SQLiteTenantStorage(tmp_path / "tenant-error.sqlite3")
    dispatcher = TenantNotificationDispatcher(TenantScopedEcosystemState(storage))
    owner = TenantContext("tenant-1", "subject-1")
    event = EcosystemNotification(
        notification_id="provider-secret-error", kind=NotificationKind.SECURITY,
        severity=NotificationSeverity.CRITICAL, title="Falha", message="Falha no provedor",
    )
    dispatcher.publish(owner, event)
    claim_time = time.time() + 1.0
    item = dispatcher.outbox.claim_due(now=claim_time, lease_seconds=30.0)[0]
    dispatcher.outbox.mark_failed(
        item, RuntimeError("Bearer super-secret-value customer=email@example.com"),
        now=claim_time + 1.0,
    )
    with storage._connect() as db:
        row = db.execute(
            "SELECT last_error FROM tenant_notification_outbox WHERE tenant_id=? AND subject_id=? AND notification_id=?",
            ("tenant-1", "subject-1", "provider-secret-error"),
        ).fetchone()
    assert row["last_error"] == "RuntimeError"
    assert "super-secret-value" not in row["last_error"]
    assert "email@example.com" not in row["last_error"]



def test_worker_status_does_not_expose_other_tenants_queue_counts(tmp_path):
    storage = SQLiteTenantStorage(tmp_path / "tenant.sqlite3")
    dispatcher = TenantNotificationDispatcher(TenantScopedEcosystemState(storage))
    alice = TenantContext("tenant-1", "alice")
    bob = TenantContext("tenant-1", "bob")
    event = EcosystemNotification(
        notification_id="private-count", kind=NotificationKind.SECURITY,
        severity=NotificationSeverity.INFO, title="Aviso", message="Privado",
    )
    dispatcher.publish(alice, event)
    worker = TenantNotificationOutboxWorker(dispatcher.outbox, _Sink())
    assert worker.status(alice)["outbox"]["PENDING"] == 1
    assert worker.status(bob)["outbox"]["PENDING"] == 0



import pytest


@pytest.mark.parametrize("bad", [True, float("nan"), float("inf"), float("-inf"), 10**1000, "1"])
def test_worker_rejects_invalid_poll_intervals(tmp_path, bad):
    storage = SQLiteTenantStorage(tmp_path / "tenant.sqlite3")
    dispatcher = TenantNotificationDispatcher(TenantScopedEcosystemState(storage))
    with pytest.raises(ValueError):
        TenantNotificationOutboxWorker(dispatcher.outbox, _Sink(), poll_interval_seconds=bad)


@pytest.mark.parametrize("bad", [True, float("nan"), float("inf"), float("-inf"), 10**1000, "1"])
def test_worker_rejects_invalid_stop_timeouts(tmp_path, bad):
    storage = SQLiteTenantStorage(tmp_path / "tenant.sqlite3")
    dispatcher = TenantNotificationDispatcher(TenantScopedEcosystemState(storage))
    worker = TenantNotificationOutboxWorker(dispatcher.outbox, _Sink())
    with pytest.raises(ValueError):
        worker.stop(timeout=bad)


def test_worker_status_marks_stale_delivery_cycle_degraded(tmp_path):
    storage = SQLiteTenantStorage(tmp_path / "tenant-stale.sqlite3")
    dispatcher = TenantNotificationDispatcher(TenantScopedEcosystemState(storage))
    worker = TenantNotificationOutboxWorker(dispatcher.outbox, _Sink())
    worker._thread = __import__("threading").Thread(target=lambda: time.sleep(2), daemon=True)
    worker._thread.start()
    worker._last_cycle_at = time.time() - 120

    status = worker.status()

    assert status["running"] is True
    assert status["state"] == "DEGRADED"
    assert status["last_cycle_age_seconds"] >= 120
    worker.stop(timeout=3)


def test_worker_status_reports_starting_before_first_cycle(tmp_path):
    storage = SQLiteTenantStorage(tmp_path / "tenant-starting.sqlite3")
    dispatcher = TenantNotificationDispatcher(TenantScopedEcosystemState(storage))
    worker = TenantNotificationOutboxWorker(dispatcher.outbox, _Sink())
    worker._thread = __import__("threading").Thread(target=lambda: time.sleep(0.05), daemon=True)
    worker._thread.start()

    assert worker.status()["state"] == "STARTING"
    worker.stop(timeout=1)



def test_tenant_outbox_recovers_expired_lease_after_worker_restart(tmp_path):
    database = tmp_path / "tenant-restart.sqlite3"
    storage_before_restart = SQLiteTenantStorage(database)
    dispatcher_before_restart = TenantNotificationDispatcher(
        TenantScopedEcosystemState(storage_before_restart)
    )
    owner = TenantContext("tenant-1", "subject-1")
    event = EcosystemNotification(
        notification_id="restart-event", kind=NotificationKind.MARKET,
        severity=NotificationSeverity.IMPORTANT, title="EURUSD",
        message="Evento pendente após reinício",
    )
    assert dispatcher_before_restart.publish(owner, event)

    claim_time = time.time() + 1.0
    abandoned = dispatcher_before_restart.outbox.claim_due(
        now=claim_time, lease_seconds=5.0
    )[0]
    assert abandoned.attempts == 1

    # Simulate a process restart by rebuilding storage, dispatcher and outbox.
    storage_after_restart = SQLiteTenantStorage(database)
    dispatcher_after_restart = TenantNotificationDispatcher(
        TenantScopedEcosystemState(storage_after_restart)
    )
    assert dispatcher_after_restart.outbox.claim_due(now=claim_time + 4.0) == ()

    recovered = dispatcher_after_restart.outbox.claim_due(now=claim_time + 6.0)
    assert len(recovered) == 1
    assert recovered[0].notification_id == "restart-event"
    assert recovered[0].attempts == 2
    assert recovered[0].lease_token != abandoned.lease_token
    assert recovered[0].tenant_id == owner.tenant_id
    assert recovered[0].subject_id == owner.subject_id


def test_tenant_outbox_crash_recovery_respects_retry_limit(tmp_path):
    storage = SQLiteTenantStorage(tmp_path / "tenant-crash-budget.sqlite3")
    dispatcher = TenantNotificationDispatcher(TenantScopedEcosystemState(storage))
    dispatcher.outbox.max_attempts = 2
    owner = TenantContext("tenant-1", "subject-1")
    event = EcosystemNotification(
        notification_id="crash-budget-event", kind=NotificationKind.SECURITY,
        severity=NotificationSeverity.CRITICAL, title="Worker",
        message="Teste de limite de tentativas",
    )
    assert dispatcher.publish(owner, event)

    claim_time = time.time() + 1.0
    first = dispatcher.outbox.claim_due(now=claim_time, lease_seconds=5.0)[0]
    assert first.attempts == 1
    second = dispatcher.outbox.claim_due(now=claim_time + 6.0, lease_seconds=5.0)[0]
    assert second.attempts == 2

    # The second worker also crashes; the next poll dead-letters the item.
    assert dispatcher.outbox.claim_due(now=claim_time + 12.0, lease_seconds=5.0) == ()
    counts = dispatcher.outbox.status_counts(owner)
    assert counts["DEAD"] == 1
    assert counts["IN_FLIGHT"] == 0
    assert dispatcher.outbox.status_counts(TenantContext("tenant-1", "other-user"))["DEAD"] == 0


def test_tenant_outbox_old_worker_cannot_acknowledge_after_recovery(tmp_path):
    storage = SQLiteTenantStorage(tmp_path / "tenant-fencing.sqlite3")
    dispatcher = TenantNotificationDispatcher(TenantScopedEcosystemState(storage))
    owner = TenantContext("tenant-1", "subject-1")
    event = EcosystemNotification(
        notification_id="fenced-event", kind=NotificationKind.MARKET,
        severity=NotificationSeverity.INFO, title="BTCUSD",
        message="Teste de fencing",
    )
    assert dispatcher.publish(owner, event)

    claim_time = time.time() + 1.0
    old_owner = dispatcher.outbox.claim_due(now=claim_time, lease_seconds=5.0)[0]
    new_owner = dispatcher.outbox.claim_due(now=claim_time + 6.0, lease_seconds=30.0)[0]
    assert old_owner.lease_token != new_owner.lease_token

    assert dispatcher.outbox._finish(old_owner, status="DELIVERED", now=claim_time + 7.0) is False
    assert dispatcher.outbox._finish(new_owner, status="DELIVERED", now=claim_time + 7.0) is True
    assert dispatcher.outbox.status_counts(owner)["DELIVERED"] == 1
