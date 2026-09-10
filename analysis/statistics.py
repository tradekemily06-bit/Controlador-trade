from __future__ import annotations

from dataclasses import dataclass
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
