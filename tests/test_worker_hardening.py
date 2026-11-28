from types import SimpleNamespace

import pytest

from integration.news_polling_worker import NewsPollingWorker
from integration.notification_outbox_worker import NotificationOutboxWorker


class _NewsProvider:
    def __init__(self, items):
        self.items = items

    def latest(self, *, limit):
        return self.items[:limit]

    def status(self):
        return {"configured": True, "live": True}


class _Evidence:
    def ingest(self, item, *, source_id, ingested_at):
        return None


class _Sink:
    def deliver(self, idempotency_key, payload):
        return True


class _Outbox:
    def dispatch_due(self, sink, *, limit):
        raise AssertionError("worker must not start during constructor validation")

    def status_counts(self):
        return {}


def test_news_partial_item_rejection_does_not_advance_success_timestamp():
    worker = NewsPollingWorker(
        _NewsProvider([SimpleNamespace(url="http://untrusted.example/article")]),
        _Evidence(),
    )

    status = worker.run_once()

    assert status["last_state"] == "PARTIAL"
    assert status["last_processed"] == 0
    assert status["last_errors"] == 1
    assert status["last_success_at"] is None


def test_news_empty_but_successful_live_poll_advances_success_timestamp():
    worker = NewsPollingWorker(_NewsProvider([]), _Evidence())

    status = worker.run_once()

    assert status["last_state"] == "POLL_SUCCEEDED"
    assert status["last_errors"] == 0
    assert status["last_success_at"] is not None


@pytest.mark.parametrize("interval", [True, float("nan"), float("inf"), 0, 0.01, 3601])
def test_notification_worker_rejects_invalid_poll_interval(interval):
    with pytest.raises(ValueError):
        NotificationOutboxWorker(_Outbox(), _Sink(), poll_interval_seconds=interval)


@pytest.mark.parametrize("timeout", [True, float("nan"), float("inf"), -1, 61])
def test_notification_worker_rejects_invalid_stop_timeout(timeout):
    worker = NotificationOutboxWorker(_Outbox(), _Sink())

    with pytest.raises(ValueError):
        worker.stop(timeout=timeout)
