from datetime import datetime, timezone

import pytest

from analysis.economic_calendar import (
    CalendarImpact,
    CalendarStatus,
    normalize_calendar_batch,
    normalize_calendar_event,
)


def _normalize(payload, *, source_id="ecb", source_tier="OFFICIAL_PRIMARY"):
    return normalize_calendar_event(
        payload, trusted_source_id=source_id, trusted_source_tier=source_tier,
        trusted_source_hosts=("ecb.europa.eu", "example.com"),
    )


def _normalize_batch(payloads, *, source_id="ecb", source_tier="OFFICIAL_PRIMARY"):
    return normalize_calendar_batch(
        payloads, trusted_source_id=source_id, trusted_source_tier=source_tier,
        trusted_source_hosts=("ecb.europa.eu", "example.com"),
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
    event = _normalize(_event())
    assert event.scheduled_at == datetime(2026, 12, 10, 12, 15, tzinfo=timezone.utc)
    assert event.observed_at == datetime(2026, 12, 10, 13, 15, 8, tzinfo=timezone.utc)
    assert event.actual == "2.15"
    assert event.consensus is None
    assert event.impact is CalendarImpact.HIGH
    assert event.status is CalendarStatus.RELEASED


def test_revised_previous_value_is_kept_separate_from_previous():
    event = _normalize(_event(
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
        _normalize(_event(scheduled_at=timestamp))


@pytest.mark.parametrize("value", [True, "NaN", "Infinity", "not-a-number"])
def test_rejects_invalid_numeric_values(value):
    with pytest.raises(ValueError):
        _normalize(_event(actual=value))


def test_rejects_non_https_source_url_and_unknown_source_tier():
    with pytest.raises(ValueError):
        _normalize(_event(source_url="http://example.com/event"))
    with pytest.raises(ValueError):
        _normalize(_event(), source_tier="UNVERIFIED")


def test_batch_rejects_duplicate_publisher_event_ids_without_cross_source_merge():
    first = _normalize(_event())
    second = _normalize(_event(), source_id="another_provider")
    assert first.corroboration_fingerprint == second.corroboration_fingerprint
    assert first.source_key != second.source_key
    with pytest.raises(ValueError):
        _normalize_batch([_event(), _event()])
    assert len(_normalize_batch([_event()])) == 1


def test_calendar_batch_rejects_non_list_input():
    with pytest.raises(ValueError):
        _normalize_batch("not-a-batch")


@pytest.mark.parametrize(("field", "value"), [
    ("source_event_id", None),
    ("source_url", None),
    ("title", None),
    ("country_code", None),
    ("currency", 978),
])
def test_rejects_coercion_of_invalid_source_metadata(field, value):
    with pytest.raises(ValueError):
        _normalize(_event(**{field: value}))


def test_source_identity_and_tier_cannot_be_forged_by_provider_payload():
    event = _normalize(
        _event(source_id="attacker", source_tier="OFFICIAL_PRIMARY"),
        source_id="trusted-provider",
        source_tier="TRUSTED_MEDIA",
    )
    assert event.source_id == "trusted-provider"
    assert event.source_tier == "TRUSTED_MEDIA"


def test_trusted_source_identity_is_required_and_validated():
    with pytest.raises(ValueError):
        normalize_calendar_event(
            _event(), trusted_source_id=None, trusted_source_tier="OFFICIAL_PRIMARY",
            trusted_source_hosts=("ecb.europa.eu",)
        )
    with pytest.raises(ValueError):
        normalize_calendar_event(
            _event(), trusted_source_id="ecb", trusted_source_tier="UNVERIFIED",
            trusted_source_hosts=("ecb.europa.eu",)
        )


@pytest.mark.parametrize("url", [
    "https://evil.example.net/fake-release",
    "https://ecb.europa.eu.attacker.test/fake-release",
    "http://ecb.europa.eu/fake-release",
    "https://user:password@ecb.europa.eu/fake-release",
    "https://ecb.europa.eu:8443/fake-release",
])
def test_rejects_calendar_source_url_outside_trusted_host_policy(url):
    with pytest.raises(ValueError):
        _normalize(_event(source_url=url))


def test_trusted_source_host_policy_allows_exact_host_and_subdomains():
    exact = _normalize(_event())
    subdomain = _normalize(_event(source_url="https://www.ecb.europa.eu/press"))
    assert exact.source_url.startswith("https://")
    assert subdomain.source_url.startswith("https://")


def test_trusted_source_host_allowlist_is_mandatory():
    with pytest.raises(ValueError):
        normalize_calendar_event(
            _event(), trusted_source_id="ecb", trusted_source_tier="OFFICIAL_PRIMARY",
            trusted_source_hosts=(),
        )


def test_date_only_calendar_event_preserves_date_without_fabricated_midnight():
    event = _normalize(_event(
        scheduled_time_precision="DATE_ONLY",
        scheduled_date="2026-12-10",
        scheduled_at=None,
    ))

    assert event.scheduled_at is None
    assert event.scheduled_date.isoformat() == "2026-12-10"
    assert event.scheduled_time_precision.value == "DATE_ONLY"
    assert event.to_dict()["scheduled_at"] is None
    assert event.to_dict()["scheduled_date"] == "2026-12-10"


@pytest.mark.parametrize("value", [None, "2026-12-10T00:00:00Z", "not-a-date"])
def test_date_only_event_rejects_missing_or_timestamp_shaped_calendar_date(value):
    with pytest.raises(ValueError):
        _normalize(_event(
            scheduled_time_precision="DATE_ONLY",
            scheduled_date=value,
            scheduled_at=None,
        ))


def test_date_only_event_requires_explicit_precision_and_date():
    with pytest.raises(ValueError):
        _normalize(_event(scheduled_at="2026-12-10"))
