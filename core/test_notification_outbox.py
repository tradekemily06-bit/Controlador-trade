import pytest

from core.notification_outbox import PersistentNotificationOutbox


class RecordingSink:
    def __init__(self):
        self.messages = []

    def deliver(self, idempotency_key, payload):
        self.messages.append((idempotency_key, dict(payload)))


def test_enqueue_is_durable_and_idempotent(tmp_path):
    path = tmp_path / "outbox.sqlite3"
    outbox = PersistentNotificationOutbox(path)

    assert outbox.enqueue("event-1", {"title": "Market alert"}, now=10)
    assert not outbox.enqueue("event-1", {"title": "duplicate"}, now=11)

    restored = PersistentNotificationOutbox(path)
    claimed = restored.claim_due(now=12)

    assert len(claimed) == 1
    assert claimed[0].payload == {"title": "Market alert"}
    assert claimed[0].attempts == 1


def test_dispatch_marks_success_and_keeps_payload(tmp_path):
    outbox = PersistentNotificationOutbox(tmp_path / "outbox.sqlite3")
    sink = RecordingSink()
    outbox.enqueue("event-1", {"title": "System update"}, now=100)

    result = outbox.dispatch_due(sink, now=101)

    assert result.claimed == 1
    assert result.delivered == 1
    assert result.retried == 0
    assert sink.messages == [("event-1", {"title": "System update"})]
    assert outbox.status_counts() == {
        "PENDING": 0, "IN_FLIGHT": 0, "DELIVERED": 1, "DEAD": 0
    }


def test_failed_delivery_is_retried_with_backoff(tmp_path):
    outbox = PersistentNotificationOutbox(
        tmp_path / "outbox.sqlite3", base_backoff_seconds=5, max_backoff_seconds=20
    )

    class FailingSink:
        def deliver(self, idempotency_key, payload):
            raise RuntimeError("temporary provider failure")

    outbox.enqueue("event-1", {"title": "Alert"}, now=100)
    first = outbox.dispatch_due(FailingSink(), now=101)

    assert first.retried == 1
    assert outbox.claim_due(now=105) == ()
    second_claim = outbox.claim_due(now=106)
    assert len(second_claim) == 1
    assert second_claim[0].attempts == 2


def test_delivery_moves_to_dead_letter_after_max_attempts(tmp_path):
    outbox = PersistentNotificationOutbox(
        tmp_path / "outbox.sqlite3", max_attempts=2, base_backoff_seconds=1
    )

    class FailingSink:
        def deliver(self, idempotency_key, payload):
            raise RuntimeError("provider unavailable")

    outbox.enqueue("event-1", {"title": "Alert"}, now=0)
    assert outbox.dispatch_due(FailingSink(), now=0).retried == 1
    assert outbox.dispatch_due(FailingSink(), now=1).dead_lettered == 1
    assert outbox.status_counts()["DEAD"] == 1


def test_expired_lease_can_be_reclaimed_after_worker_crash(tmp_path):
    outbox = PersistentNotificationOutbox(tmp_path / "outbox.sqlite3")
    outbox.enqueue("event-1", {"title": "Alert"}, now=10)

    first = outbox.claim_due(now=11, lease_seconds=5)
    assert first[0].attempts == 1
    assert outbox.claim_due(now=15) == ()

    reclaimed = outbox.claim_due(now=16)
    assert len(reclaimed) == 1
    assert reclaimed[0].attempts == 2


def test_invalid_inputs_are_rejected(tmp_path):
    outbox = PersistentNotificationOutbox(tmp_path / "outbox.sqlite3")

    with pytest.raises(ValueError):
        outbox.enqueue("", {"title": "Alert"})
    with pytest.raises(ValueError):
        outbox.enqueue("event-1", [])
    with pytest.raises(ValueError):
        outbox.claim_due(limit=0)
    with pytest.raises(ValueError):
        outbox.dispatch_due(object())



def test_failure_diagnostics_redact_urls_and_credentials(tmp_path):
    outbox = PersistentNotificationOutbox(
        tmp_path / "outbox.sqlite3", max_attempts=1
    )

    class LeakyFailingSink:
        def deliver(self, idempotency_key, payload):
            raise RuntimeError(
                "push failed https://push.example.test/send/private "
                "Bearer super-secret authorization=top-secret "
                "p256dh=private-key-value"
            )

    outbox.enqueue("event-secret", {"title": "Alert"}, now=10)
    result = outbox.dispatch_due(LeakyFailingSink(), now=11)
    assert result.dead_lettered == 1

    import sqlite3
    with sqlite3.connect(tmp_path / "outbox.sqlite3") as db:
        error = db.execute(
            "SELECT last_error FROM notification_outbox WHERE idempotency_key=?",
            ("event-secret",),
        ).fetchone()[0]

    assert "push.example.test" not in error
    assert "super-secret" not in error
    assert "top-secret" not in error
    assert "private-key-value" not in error
    assert "[URL REDACTED]" in error
    assert "Bearer [REDACTED]" in error



def test_expired_outbox_owner_cannot_acknowledge_or_fail_reclaimed_event(tmp_path):
    outbox = PersistentNotificationOutbox(tmp_path / "outbox.sqlite3")
    outbox.enqueue("lease-fenced-event", {"title": "Alert"}, now=10)

    old_owner = outbox.claim_due(now=11, lease_seconds=5)[0]
    new_owner = outbox.claim_due(now=17, lease_seconds=30)[0]

    assert old_owner.lease_token != new_owner.lease_token
    assert outbox.mark_delivered(
        old_owner.idempotency_key, old_owner.lease_token, now=18
    ) is False
    with pytest.raises(ValueError):
        outbox.mark_failed(
            old_owner.idempotency_key, old_owner.lease_token,
            "late failure from expired worker", now=18,
        )

    assert outbox.status_counts()["IN_FLIGHT"] == 1
    assert outbox.mark_delivered(
        new_owner.idempotency_key, new_owner.lease_token, now=19
    ) is True
    assert outbox.status_counts()["DELIVERED"] == 1



def test_outbox_owner_cannot_acknowledge_after_lease_expiry_without_reclaim(tmp_path):
    outbox = PersistentNotificationOutbox(tmp_path / "outbox.sqlite3")
    outbox.enqueue("expired-only-event", {"title": "Alert"}, now=10)
    owner = outbox.claim_due(now=11, lease_seconds=5)[0]

    assert outbox.mark_delivered(
        owner.idempotency_key, owner.lease_token, now=16
    ) is False
    with pytest.raises(ValueError):
        outbox.mark_failed(
            owner.idempotency_key, owner.lease_token,
            "late provider failure", now=16,
        )
    assert outbox.status_counts()["IN_FLIGHT"] == 1
    reclaimed = outbox.claim_due(now=17, lease_seconds=30)
    assert len(reclaimed) == 1
    assert reclaimed[0].lease_token != owner.lease_token


def test_crashed_worker_reclaims_consume_retry_budget_and_dead_letter(tmp_path):
    outbox = PersistentNotificationOutbox(
        tmp_path / "outbox.sqlite3", max_attempts=2
    )
    outbox.enqueue("crash-loop-event", {"title": "Alert"}, now=10)

    first_owner = outbox.claim_due(now=11, lease_seconds=5)[0]
    assert first_owner.attempts == 1
    # The first worker crashes. A second worker gets one final attempt.
    second_owner = outbox.claim_due(now=17, lease_seconds=5)[0]
    assert second_owner.attempts == 2

    # The second worker also crashes. The next poll must dead-letter the event
    # rather than retrying forever or dispatching beyond max_attempts.
    assert outbox.claim_due(now=23, lease_seconds=5) == ()
    assert outbox.status_counts()["DEAD"] == 1
    assert outbox.status_counts()["IN_FLIGHT"] == 0


def test_lost_lease_does_not_abort_remaining_batch_items(tmp_path):
    import sqlite3

    path = tmp_path / "outbox.sqlite3"
    outbox = PersistentNotificationOutbox(path)
    outbox.enqueue("lease-lost", {"title": "First"}, now=10)
    outbox.enqueue("still-valid", {"title": "Second"}, now=10)

    class LeaseExpiringSink:
        def __init__(self):
            self.delivered = []

        def deliver(self, idempotency_key, payload):
            if idempotency_key == "lease-lost":
                with sqlite3.connect(path) as db:
                    db.execute(
                        "UPDATE notification_outbox SET lease_until=0 "
                        "WHERE idempotency_key=?",
                        (idempotency_key,),
                    )
                raise RuntimeError("provider failed after lease expiry")
            self.delivered.append((idempotency_key, dict(payload)))

    sink = LeaseExpiringSink()
    result = outbox.dispatch_due(sink, now=100, lease_seconds=60)

    assert result.claimed == 2
    assert result.delivered == 1
    assert result.retried == 0
    assert result.dead_lettered == 0
    assert sink.delivered == [("still-valid", {"title": "Second"})]
    counts = outbox.status_counts()
    assert counts["DELIVERED"] == 1
    assert counts["IN_FLIGHT"] == 1
