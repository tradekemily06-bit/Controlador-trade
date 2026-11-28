"""Strict normalization for source-backed macroeconomic calendar events.

This module intentionally does not fetch data, invent consensus values, infer
market direction, or merge reports from different publishers. Provider
adapters must supply source provenance and timezone-aware timestamps.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from enum import Enum
import hashlib
import re
from typing import Any, Mapping
from urllib.parse import urlparse


class CalendarImpact(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    UNKNOWN = "UNKNOWN"


class CalendarStatus(str, Enum):
    SCHEDULED = "SCHEDULED"
    RELEASED = "RELEASED"
    REVISED = "REVISED"
    CANCELLED = "CANCELLED"


_CURRENCY = re.compile(r"^[A-Z]{3}$")
_COUNTRY = re.compile(r"^[A-Z]{2}$")
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


def _required_text(value: Any, field: str, *, max_length: int = 512) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be text")
    result = value.strip()
    if not result or len(result) > max_length:
        raise ValueError(f"{field} must contain 1 to {max_length} characters")
    return result


def _timestamp(value: Any, field: str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        raw = value.strip()
        try:
            parsed = datetime.fromisoformat(raw[:-1] + "+00:00" if raw.endswith("Z") else raw)
        except ValueError as exc:
            raise ValueError(f"{field} must be an ISO-8601 timestamp") from exc
    else:
        raise ValueError(f"{field} is required")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field} must include a timezone offset")
    return parsed.astimezone(timezone.utc)


def _optional_decimal(value: Any, field: str) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a finite numeric value or null")
    try:
        number = Decimal(str(value).strip())
    except (InvalidOperation, ValueError, AttributeError) as exc:
        raise ValueError(f"{field} must be a finite numeric value or null") from exc
    if not number.is_finite():
        raise ValueError(f"{field} must be finite")
    return format(number, "f")


@dataclass(frozen=True)
class EconomicCalendarEvent:
    source_id: str
    source_event_id: str
    source_url: str
    source_tier: str
    title: str
    country_code: str
    currency: str | None
    scheduled_at: datetime
    observed_at: datetime
    impact: CalendarImpact
    status: CalendarStatus
    actual: str | None = None
    consensus: str | None = None
    previous: str | None = None
    revised_previous: str | None = None
    revision_note: str | None = None

    def __post_init__(self) -> None:
        for name in ("source_id", "source_event_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
                raise ValueError(f"{name} is invalid")
        if not isinstance(self.title, str) or not self.title.strip() or len(self.title) > 240:
            raise ValueError("title must contain 1 to 240 characters")
        if not _COUNTRY.fullmatch(self.country_code) and self.country_code != "EU":
            raise ValueError("country_code must be an ISO-3166 alpha-2 code or the EU macro-area code")
        if self.currency is not None and not _CURRENCY.fullmatch(self.currency):
            raise ValueError("currency must be an ISO-4217 alpha-3 code or null")
        if not isinstance(self.impact, CalendarImpact) or not isinstance(self.status, CalendarStatus):
            raise ValueError("impact and status must use the supported enums")
        parsed_url = urlparse(self.source_url)
        if parsed_url.scheme != "https" or not parsed_url.netloc or parsed_url.username or parsed_url.password:
            raise ValueError("source_url must be an HTTPS URL without embedded credentials")
        if self.source_tier not in {"OFFICIAL_PRIMARY", "TRUSTED_MEDIA", "PROVIDER"}:
            raise ValueError("source_tier is not supported")
        if self.scheduled_at.tzinfo is None or self.observed_at.tzinfo is None:
            raise ValueError("calendar timestamps must be timezone-aware")

    @property
    def source_key(self) -> str:
        """Publisher-scoped identity; never merges different publishers."""
        return f"{self.source_id}:{self.source_event_id}"

    @property
    def corroboration_fingerprint(self) -> str:
        """Candidate cross-source match only; callers must verify before merging."""
        canonical = "|".join((
            " ".join(self.title.casefold().split()),
            self.country_code,
            self.scheduled_at.astimezone(timezone.utc).isoformat(),
        ))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["scheduled_at"] = self.scheduled_at.astimezone(timezone.utc).isoformat()
        result["observed_at"] = self.observed_at.astimezone(timezone.utc).isoformat()
        result["impact"] = self.impact.value
        result["status"] = self.status.value
        result["source_key"] = self.source_key
        result["corroboration_fingerprint"] = self.corroboration_fingerprint
        return result


def normalize_calendar_event(
    payload: Mapping[str, Any], *, trusted_source_id: str, trusted_source_tier: str,
    trusted_source_hosts: tuple[str, ...] | list[str],
) -> EconomicCalendarEvent:
    """Normalize one event using source identity/tier supplied by trusted host config."""
    if not isinstance(payload, Mapping):
        raise ValueError("calendar event must be an object")
    try:
        impact = CalendarImpact(str(payload.get("impact", "UNKNOWN")).upper())
        status = CalendarStatus(str(payload.get("status", "SCHEDULED")).upper())
    except ValueError as exc:
        raise ValueError("unsupported calendar impact or status") from exc

    if not isinstance(trusted_source_hosts, (tuple, list)) or not trusted_source_hosts:
        raise ValueError("trusted_source_hosts must be a non-empty allowlist")
    allowed_hosts = []
    for host in trusted_source_hosts:
        if not isinstance(host, str) or not host.strip():
            raise ValueError("trusted source host allowlist contains an invalid host")
        normalized_host = host.strip().lower().rstrip(".")
        if "/" in normalized_host or ":" in normalized_host or "@" in normalized_host:
            raise ValueError("trusted source host must be a hostname only")
        allowed_hosts.append(normalized_host)

    source_url = _required_text(payload.get("source_url"), "source_url", max_length=2048)
    parsed_source_url = urlparse(source_url)
    source_host = (parsed_source_url.hostname or "").lower().rstrip(".")
    if (
        parsed_source_url.scheme.lower() != "https"
        or not source_host
        or parsed_source_url.username
        or parsed_source_url.password
        or parsed_source_url.port not in (None, 443)
        or not any(source_host == host or source_host.endswith("." + host) for host in allowed_hosts)
    ):
        raise ValueError("source_url host is not allowed for this trusted source")

    currency_value = payload.get("currency")
    if currency_value is not None and not isinstance(currency_value, str):
        raise ValueError("currency must be text or null")
    currency = currency_value.strip().upper() if currency_value is not None else None
    revision_note = payload.get("revision_note")
    if revision_note is not None:
        revision_note = str(revision_note).strip()[:500] or None

    return EconomicCalendarEvent(
        source_id=_required_text(trusted_source_id, "trusted_source_id", max_length=128),
        source_event_id=_required_text(payload.get("source_event_id"), "source_event_id", max_length=128),
        source_url=source_url,
        source_tier=_required_text(trusted_source_tier, "trusted_source_tier", max_length=32).upper(),
        title=_required_text(payload.get("title"), "title", max_length=240),
        country_code=_required_text(payload.get("country_code"), "country_code", max_length=2).upper(),
        currency=currency,
        scheduled_at=_timestamp(payload.get("scheduled_at"), "scheduled_at"),
        observed_at=_timestamp(payload.get("observed_at"), "observed_at"),
        impact=impact,
        status=status,
        actual=_optional_decimal(payload.get("actual"), "actual"),
        consensus=_optional_decimal(payload.get("consensus"), "consensus"),
        previous=_optional_decimal(payload.get("previous"), "previous"),
        revised_previous=_optional_decimal(payload.get("revised_previous"), "revised_previous"),
        revision_note=revision_note,
    )


def normalize_calendar_batch(
    payloads: Any, *, trusted_source_id: str, trusted_source_tier: str,
    trusted_source_hosts: tuple[str, ...] | list[str],
) -> list[EconomicCalendarEvent]:
    """Normalize a batch under one trusted source identity; reject duplicate IDs."""
    if isinstance(payloads, (str, bytes)) or not isinstance(payloads, (list, tuple)):
        raise ValueError("calendar batch must be a list or tuple")
    events = [
        normalize_calendar_event(
            item, trusted_source_id=trusted_source_id,
            trusted_source_tier=trusted_source_tier,
            trusted_source_hosts=trusted_source_hosts,
        )
        for item in payloads
    ]
    keys = [event.source_key for event in events]
    if len(keys) != len(set(keys)):
        raise ValueError("duplicate source event ID in calendar batch")
    return events
