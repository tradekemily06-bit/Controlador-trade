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
