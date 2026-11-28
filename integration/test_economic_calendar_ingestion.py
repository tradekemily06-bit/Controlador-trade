from datetime import datetime, timezone

import pytest

from analysis.economic_calendar import normalize_calendar_event
from integration.economic_calendar_ingestion import (
    EconomicCalendarIngestionService,
    SQLiteEconomicCalendarStore,
)


def _payload(**changes):
    value = {
        "source_event_id": "us-cpi-2026-11",
        "source_url": "https://www.bls.gov/news.release/cpi.htm",
        "title": "US Consumer Price Index",
        "country_code": "US",
        "currency": "USD",
        "scheduled_at": "2026-11-28T08:30:00-05:00",
        "observed_at": "2026-11-28T13:30:05Z",
        "impact": "HIGH",
        "status": "RELEASED",
        "actual": "2.7",
        "consensus": None,
        "previous": "2.9",
        "revised_previous": None,
    }
    value.update(changes)
    return value


def _service(path):
    store = SQLiteEconomicCalendarStore(path)
    store.initialize_schema()
    service = EconomicCalendarIngestionService(
        store=store,
        trusted_sources={
            "bls": {
                "source_tier": "OFFICIAL_PRIMARY",
                "allowed_hosts": ("bls.gov",),
            }
        },
    )
    return store, service


def test_ingestion_normalizes_trusted_source_and_persists_event(tmp_path):
    store, service = _service(tmp_path / "calendar.sqlite3")

    result = service.ingest(source_id="bls", payloads=[_payload()])

    assert result["received"] == 1
    assert result["inserted"] == 1
    assert result["duplicates_ignored"] == 0
    assert result["durable_store"] == "LOCAL_SQLITE_SINGLE_RUNTIME"
    assert result["execution_authorized"] is False
    records = store.list_latest(
        start_at="2026-11-28T13:00:00Z",
        end_at="2026-11-28T14:00:00Z",
    )
    assert records[0]["source_id"] == "bls"
    assert records[0]["source_tier"] == "OFFICIAL_PRIMARY"
    assert records[0]["consensus"] is None


def test_same_observation_is_idempotent_and_revision_is_append_only(tmp_path):
    store, service = _service(tmp_path / "calendar.sqlite3")
    service.ingest(source_id="bls", payloads=[_payload()])
    duplicate = service.ingest(source_id="bls", payloads=[_payload()])
    revision = service.ingest(
        source_id="bls",
        payloads=[_payload(
            observed_at="2026-11-28T13:35:00Z",
            status="REVISED",
            revised_previous="2.8",
            revision_note="Publisher correction",
        )],
    )

    assert duplicate["inserted"] == 0
    assert duplicate["duplicates_ignored"] == 1
    assert revision["inserted"] == 1
    latest = store.list_latest(
        start_at="2026-11-28T13:00:00Z",
        end_at="2026-11-28T14:00:00Z",
    )
    assert len(latest) == 1
    assert latest[0]["status"] == "REVISED"
    assert latest[0]["previous"] == "2.9"
    assert latest[0]["revised_previous"] == "2.8"


def test_same_event_id_from_another_publisher_is_not_merged(tmp_path):
    store = SQLiteEconomicCalendarStore(tmp_path / "calendar.sqlite3")
    store.initialize_schema()
    first = normalize_calendar_event(
        _payload(), trusted_source_id="bls", trusted_source_tier="OFFICIAL_PRIMARY",
        trusted_source_hosts=("bls.gov",),
    )
    second_payload = _payload(source_url="https://www.bea.gov/news/2026/personal-income")
    second = normalize_calendar_event(
        second_payload, trusted_source_id="bea", trusted_source_tier="OFFICIAL_PRIMARY",
        trusted_source_hosts=("bea.gov",),
    )

    assert first.source_event_id == second.source_event_id
    assert first.source_key != second.source_key
    assert store.append_batch([first, second]) == 2


def test_calendar_source_must_be_configured_and_trusted(tmp_path):
    store = SQLiteEconomicCalendarStore(tmp_path / "calendar.sqlite3")
    store.initialize_schema()
    service = EconomicCalendarIngestionService(store=store, trusted_sources={"bls": {
        "source_tier": "OFFICIAL_PRIMARY",
        "allowed_hosts": ("bls.gov",),
    }})
    with pytest.raises(ValueError):
        service.ingest(source_id="unknown", payloads=[_payload()])
    with pytest.raises(ValueError):
        service.ingest(source_id="bls", payloads=[_payload(
            source_url="https://bls.gov.attacker.test/fake",
        )])


@pytest.mark.parametrize("start,end", [
    ("2026-11-28T13:00:00", "2026-11-28T14:00:00Z"),
    ("not-a-time", "2026-11-28T14:00:00Z"),
    ("2026-11-28T14:00:00Z", "2026-11-28T13:00:00Z"),
])
def test_calendar_query_requires_ordered_timezone_aware_range(tmp_path, start, end):
    store, _ = _service(tmp_path / "calendar.sqlite3")
    with pytest.raises(ValueError):
        store.list_latest(start_at=start, end_at=end)


def test_calendar_store_rejects_symlink_database_path(tmp_path):
    target = tmp_path / "target.sqlite3"
    target.touch()
    link = tmp_path / "calendar-link.sqlite3"
    link.symlink_to(target)
    with pytest.raises(ValueError):
        SQLiteEconomicCalendarStore(link)



def test_calendar_polling_worker_ingests_only_host_configured_sources(tmp_path):
    from integration.economic_calendar_ingestion import EconomicCalendarPollingWorker

    store, service = _service(tmp_path / "calendar-worker.sqlite3")
    worker = EconomicCalendarPollingWorker(
        service,
        {"bls": lambda: [_payload()]},
        interval_seconds=30,
    )

    status = worker.run_once()

    assert status["bls"]["state"] == "INGESTED"
    assert status["bls"]["received"] == 1
    assert status["bls"]["inserted"] == 1
    assert worker.status()["last_cycle_at"] is not None
    assert worker.status()["worker_running"] is False
    assert store.list_latest(
        start_at="2026-11-28T13:00:00Z",
        end_at="2026-11-28T14:00:00Z",
    )


def test_calendar_polling_worker_is_idempotent_and_isolates_source_failure(tmp_path):
    from integration.economic_calendar_ingestion import EconomicCalendarPollingWorker

    _, service = _service(tmp_path / "calendar-worker.sqlite3")
    worker = EconomicCalendarPollingWorker(
        service,
        {"bls": lambda: [_payload()]},
        interval_seconds=30,
    )

    first = worker.run_once()
    second = worker.run_once()

    assert first["bls"]["inserted"] == 1
    assert second["bls"]["state"] == "NO_NEW_OBSERVATIONS"
    assert second["bls"]["duplicates_ignored"] == 1


def test_calendar_polling_worker_records_fetch_failure_without_stopping_other_sources(tmp_path):
    from integration.economic_calendar_ingestion import EconomicCalendarPollingWorker

    store = SQLiteEconomicCalendarStore(tmp_path / "calendar-worker.sqlite3")
    store.initialize_schema()
    service = EconomicCalendarIngestionService(
        store=store,
        trusted_sources={
            "bls": {"source_tier": "OFFICIAL_PRIMARY", "allowed_hosts": ("bls.gov",)},
            "bea": {"source_tier": "OFFICIAL_PRIMARY", "allowed_hosts": ("bea.gov",)},
        },
    )
    worker = EconomicCalendarPollingWorker(
        service,
        {
            "bls": lambda: (_ for _ in ()).throw(TimeoutError("private endpoint detail")),
            "bea": lambda: [_payload(source_url="https://www.bea.gov/news/2026/personal-income")],
        },
        interval_seconds=30,
    )

    status = worker.run_once()

    assert status["bls"]["state"] == "SOURCE_UNAVAILABLE"
    assert status["bls"]["last_error_class"] == "TimeoutError"
    assert "private endpoint detail" not in str(status)
    assert status["bea"]["state"] == "INGESTED"


def test_calendar_polling_worker_rejects_untrusted_fetcher_and_interval(tmp_path):
    from integration.economic_calendar_ingestion import EconomicCalendarPollingWorker

    _, service = _service(tmp_path / "calendar-worker.sqlite3")
    with pytest.raises(ValueError):
        EconomicCalendarPollingWorker(service, {"unconfigured": lambda: []})
    with pytest.raises(ValueError):
        EconomicCalendarPollingWorker(service, {"bls": lambda: []}, interval_seconds=1)



def test_calendar_polling_worker_starts_and_stops_cleanly(tmp_path):
    from threading import Event

    from integration.economic_calendar_ingestion import EconomicCalendarPollingWorker

    _, service = _service(tmp_path / "calendar-worker.sqlite3")
    fetched = Event()

    def fetch():
        fetched.set()
        return [_payload()]

    worker = EconomicCalendarPollingWorker(
        service, {"bls": fetch}, interval_seconds=30
    )
    worker.start()

    assert fetched.wait(timeout=2)
    worker.stop(timeout=2)

    assert worker.status()["worker_running"] is False
    assert worker.status()["sources"]["bls"]["state"] == "INGESTED"


@pytest.mark.parametrize("timeout", [True, float("nan"), float("inf"), -1, 61])
def test_calendar_polling_worker_rejects_invalid_shutdown_timeout(tmp_path, timeout):
    from integration.economic_calendar_ingestion import EconomicCalendarPollingWorker

    _, service = _service(tmp_path / "calendar-worker-stop.sqlite3")
    worker = EconomicCalendarPollingWorker(
        service, {"bls": lambda: [_payload()]}, interval_seconds=30
    )

    with pytest.raises(ValueError, match="timeout"):
        worker.stop(timeout=timeout)


def test_calendar_polling_worker_accepts_zero_shutdown_timeout(tmp_path):
    from integration.economic_calendar_ingestion import EconomicCalendarPollingWorker

    _, service = _service(tmp_path / "calendar-worker-zero-stop.sqlite3")
    worker = EconomicCalendarPollingWorker(
        service, {"bls": lambda: [_payload()]}, interval_seconds=30
    )

    worker.stop(timeout=0)

    assert worker.status()["worker_running"] is False
