from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable

from analysis.decision_record import DecisionRecord


@dataclass(frozen=True)
class DecisionStatistics:
    total: int
    actionable: int
    wins: int
    losses: int
    draws: int
    open: int
    win_rate: float


def summarize(records: Iterable[DecisionRecord]) -> DecisionStatistics:
    items = list(records)
    wins = sum(r.outcome == "WIN" for r in items)
    losses = sum(r.outcome == "LOSS" for r in items)
    draws = sum(r.outcome == "DRAW" for r in items)
    opened = sum(r.outcome == "OPEN" for r in items)
    actionable = sum(r.is_actionable for r in items)
    closed = wins + losses
    return DecisionStatistics(
        total=len(items),
        actionable=actionable,
        wins=wins,
        losses=losses,
        draws=draws,
        open=opened,
        win_rate=(wins / closed * 100) if closed else 0.0,
    )


def _created_at(record: DecisionRecord) -> datetime:
    value = record.created_at
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _bucket(records: Iterable[DecisionRecord], start: datetime, end: datetime) -> dict[str, object]:
    items = [record for record in records if start <= _created_at(record) < end]
    return asdict(summarize(items))


def summarize_periods(
    records: Iterable[DecisionRecord],
    *,
    now: datetime | None = None,
) -> dict[str, dict[str, object]]:
    """Return deterministic daily, weekly and monthly statistics in UTC."""
    items = list(records)
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    current = current.astimezone(timezone.utc)

    day_start = current.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = day_start - timedelta(days=day_start.weekday())
    month_start = day_start.replace(day=1)
    if month_start.month == 12:
        next_month = month_start.replace(year=month_start.year + 1, month=1)
    else:
        next_month = month_start.replace(month=month_start.month + 1)

    return {
        "daily": _bucket(items, day_start, day_start + timedelta(days=1)),
        "weekly": _bucket(items, week_start, week_start + timedelta(days=7)),
        "monthly": _bucket(items, month_start, next_month),
    }


def summarize_breakdowns(records: Iterable[DecisionRecord]) -> dict[str, dict[str, dict[str, object]]]:
    """Summarize outcomes by symbol and timeframe for learning and audit."""
    items = list(records)

    def grouped(key: str) -> dict[str, dict[str, object]]:
        groups: dict[str, list[DecisionRecord]] = {}
        for record in items:
            value = getattr(record, key)
            label = str(value or "UNKNOWN")
            groups.setdefault(label, []).append(record)
        return {label: asdict(summarize(group)) for label, group in sorted(groups.items())}

    return {
        "symbols": grouped("symbol"),
        "timeframes": grouped("timeframe"),
    }
