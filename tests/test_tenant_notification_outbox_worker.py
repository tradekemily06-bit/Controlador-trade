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
