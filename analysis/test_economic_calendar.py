from datetime import datetime, timezone

import pytest

from analysis.economic_calendar import (
    CalendarImpact,
    CalendarStatus,
    normalize_calendar_batch,
    normalize_calendar_event,
)


def _event(**overrides):
    payload = {
        "source_id": "ecb",
        "source_event_id": "main-refinancing-rate-2026-12",
        "source_url": "https://www.ecb.europa.eu/press/pr/date/2026/html/index.en.html",
        "source_tier": "OFFICIAL_PRIMARY",
        "title": "ECB Main Refinancing Rate",
        "country_code": "EU",
        "currency": "EUR",
        "scheduled_at": "2026-12-10T13:15:00+01:00",
        "observed_at": "2026-12-10T13:15:08Z",
        "impact": "HIGH",
        "status": "RELEASED",
        "actual": "2.15",
        "consensus": None,
        "previous": "2.40",
        "revised_previous": None,
    }
    payload.update(overrides)
    return payload


def test_normalizes_timezone_and_preserves_missing_consensus():
    event = normalize_calendar_event(_event())
    assert event.scheduled_at == datetime(2026, 12, 10, 12, 15, tzinfo=timezone.utc)
    assert event.observed_at == datetime(2026, 12, 10, 13, 15, 8, tzinfo=timezone.utc)
    assert event.actual == "2.15"
    assert event.consensus is None
    assert event.impact is CalendarImpact.HIGH
    assert event.status is CalendarStatus.RELEASED


def test_revised_previous_value_is_kept_separate_from_previous():
    event = normalize_calendar_event(_event(
        status="REVISED",
        previous="2.40",
        revised_previous="2.35",
        revision_note="Prior month revised by source",
    ))
    assert event.previous == "2.40"
    assert event.revised_previous == "2.35"
    assert event.revision_note == "Prior month revised by source"


@pytest.mark.parametrize("timestamp", ["2026-12-10T13:15:00", "not-a-date", None])
def test_rejects_missing_or_timezone_naive_scheduled_timestamp(timestamp):
    with pytest.raises(ValueError):
        normalize_calendar_event(_event(scheduled_at=timestamp))


@pytest.mark.parametrize("value", [True, "NaN", "Infinity", "not-a-number"])
def test_rejects_invalid_numeric_values(value):
    with pytest.raises(ValueError):
        normalize_calendar_event(_event(actual=value))


def test_rejects_non_https_source_url_and_unknown_source_tier():
    with pytest.raises(ValueError):
        normalize_calendar_event(_event(source_url="http://example.com/event"))
    with pytest.raises(ValueError):
        normalize_calendar_event(_event(source_tier="UNVERIFIED"))


def test_batch_rejects_duplicate_publisher_event_ids_without_cross_source_merge():
    first = normalize_calendar_event(_event())
    second = normalize_calendar_event(_event(source_id="another_provider"))
    assert first.corroboration_fingerprint == second.corroboration_fingerprint
    assert first.source_key != second.source_key
    with pytest.raises(ValueError):
        normalize_calendar_batch([_event(), _event()])
    assert len(normalize_calendar_batch([_event(), _event(source_id="another_provider")])) == 2


def test_calendar_batch_rejects_non_list_input():
    with pytest.raises(ValueError):
        normalize_calendar_batch("not-a-batch")


@pytest.mark.parametrize(("field", "value"), [
    ("source_id", None),
    ("source_event_id", None),
    ("source_url", None),
    ("title", None),
    ("country_code", None),
    ("currency", 978),
])
def test_rejects_coercion_of_invalid_source_metadata(field, value):
    with pytest.raises(ValueError):
        normalize_calendar_event(_event(**{field: value}))
