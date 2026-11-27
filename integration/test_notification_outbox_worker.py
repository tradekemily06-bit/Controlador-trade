from __future__ import annotations

import time

from core.notification_outbox import PersistentNotificationOutbox
from integration.notification_outbox_worker import NotificationOutboxWorker


class RecordingSink:
    def __init__(self):
        self.messages = []

    def deliver(self, idempotency_key, payload):
        self.messages.append((idempotency_key, dict(payload)))


def test_worker_dispatches_queued_notification_and_stops(tmp_path):
    outbox = PersistentNotificationOutbox(tmp_path / "outbox.sqlite3")
    sink = RecordingSink()
    outbox.enqueue("worker-event", {"title": "Market changed"})

    worker = NotificationOutboxWorker(
        outbox, sink, poll_interval_seconds=0.01, batch_size=5
    )
    worker.start()
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline and not sink.messages:
        time.sleep(0.01)
    worker.stop()

    assert sink.messages == [("worker-event", {"title": "Market changed"})]
    assert worker.status()["running"] is False
    assert outbox.status_counts()["DELIVERED"] == 1


def test_worker_start_is_idempotent(tmp_path):
    outbox = PersistentNotificationOutbox(tmp_path / "outbox.sqlite3")
    worker = NotificationOutboxWorker(
        outbox, RecordingSink(), poll_interval_seconds=0.05
    )
    worker.start()
    first = worker._thread
    worker.start()
    assert worker._thread is first
    worker.stop()



def test_worker_status_redacts_provider_error_details(tmp_path):
    outbox = PersistentNotificationOutbox(tmp_path / "outbox.sqlite3")

    class LeakyFailingSink:
        def deliver(self, idempotency_key, payload):
            raise RuntimeError(
                "failed https://push.example.test/private "
                "Bearer worker-secret api_key=hidden-value"
            )

    outbox.enqueue("worker-secret-event", {"title": "Alert"})
    worker = NotificationOutboxWorker(
        outbox, LeakyFailingSink(), poll_interval_seconds=0.01
    )
    worker.start()
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline and worker.status()["last_error"] is None:
        time.sleep(0.01)
    worker.stop()

    error = worker.status()["last_error"]
    assert error is not None
    assert "push.example.test" not in error
    assert "worker-secret" not in error
    assert "hidden-value" not in error
    assert "[URL REDACTED]" in error
