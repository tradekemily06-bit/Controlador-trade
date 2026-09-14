"""Build conservative behavioral evidence from the ecosystem's history.

A decision is not automatically an executed trade. This module therefore uses
only records with an explicit terminal execution outcome (WIN/LOSS/DRAW/VOID)
when calculating executed-trade statistics, while preserving decision history
for audit purposes.
"""
from __future__ import annotations

from datetime import datetime
from typing import Iterable

from analysis.decision_record import DecisionRecord
from core.advanced_trading_psychology import AdvancedPsychologyAssessment, AdvancedTradingPsychology, TradingBehaviorSnapshot


_EXECUTED_OUTCOMES = {"WIN", "LOSS", "DRAW", "VOID"}


class TradingPsychologyHistory:
    """Derive conservative behavioral observations from auditable history."""

    def __init__(self, engine: AdvancedTradingPsychology | None = None) -> None:
        self.engine = engine or AdvancedTradingPsychology()

    @staticmethod
    def _ordered(records: Iterable[DecisionRecord]) -> tuple[DecisionRecord, ...]:
        return tuple(sorted(records, key=lambda record: record.created_at))

    @staticmethod
    def _executed(records: Iterable[DecisionRecord]) -> tuple[DecisionRecord, ...]:
        """Return records with an explicit outcome; analysis alone is not execution."""
        return tuple(record for record in records if record.outcome in _EXECUTED_OUTCOMES)

    def snapshot(
        self,
        records: Iterable[DecisionRecord],
        *,
        urge_to_trade: int = 0,
        fatigue: int = 0,
        confidence: int = 0,
        emotional_state: str = "",
        rule_breaks: int = 0,
        impulsive_entries: int = 0,
        avoided_valid_setups: int = 0,
        confirmation_requests: int = 0,
    ) -> TradingBehaviorSnapshot:
        ordered = self._ordered(records)
        executed = self._executed(ordered)
        losses = sum(record.outcome == "LOSS" for record in executed)
        wins = sum(record.outcome == "WIN" for record in executed)
        consecutive = 0
        for record in reversed(executed):
            if record.outcome == "LOSS":
                consecutive += 1
            else:
                break

        intervals: list[float] = []
        for previous, current in zip(executed, executed[1:]):
            try:
                delta = (
                    datetime.fromisoformat(current.created_at.replace("Z", "+00:00"))
                    - datetime.fromisoformat(previous.created_at.replace("Z", "+00:00"))
                ).total_seconds()
            except ValueError:
                continue
            if delta >= 0:
                intervals.append(delta)

        repeated_after_loss = 0
        for previous, current in zip(executed, executed[1:]):
            if previous.outcome == "LOSS" and current.is_actionable:
                repeated_after_loss += 1

        return TradingBehaviorSnapshot(
            trades_count=len(executed),
            losses=losses,
            wins=wins,
            consecutive_losses=consecutive,
            avg_seconds_between_trades=(sum(intervals) / len(intervals) if intervals else None),
            rule_breaks=rule_breaks,
            impulsive_entries=impulsive_entries,
            avoided_valid_setups=avoided_valid_setups,
            repeated_entries_after_loss=repeated_after_loss,
            confirmation_requests=confirmation_requests,
            fatigue=fatigue,
            urge_to_trade=urge_to_trade,
            confidence=confidence,
            emotional_state=emotional_state,
        )

    def assess_history(self, records: Iterable[DecisionRecord], **context: object) -> AdvancedPsychologyAssessment:
        return self.engine.assess(self.snapshot(records, **context))
