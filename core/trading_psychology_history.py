"""Build behavioral evidence from the ecosystem's immutable decision history."""
from __future__ import annotations

from datetime import datetime
from typing import Iterable

from analysis.decision_record import DecisionRecord
from core.advanced_trading_psychology import AdvancedPsychologyAssessment, AdvancedTradingPsychology, TradingBehaviorSnapshot


class TradingPsychologyHistory:
    """Derive conservative behavioral observations from recorded trading decisions."""

    def __init__(self, engine: AdvancedTradingPsychology | None = None) -> None:
        self.engine = engine or AdvancedTradingPsychology()

    @staticmethod
    def _ordered(records: Iterable[DecisionRecord]) -> tuple[DecisionRecord, ...]:
        return tuple(sorted(records, key=lambda record: record.created_at))

    def snapshot(self, records: Iterable[DecisionRecord], *, urge_to_trade: int = 0, fatigue: int = 0, confidence: int = 0, emotional_state: str = "", rule_breaks: int = 0, impulsive_entries: int = 0, avoided_valid_setups: int = 0, confirmation_requests: int = 0) -> TradingBehaviorSnapshot:
        ordered = self._ordered(records)
        losses = sum(record.outcome == "LOSS" for record in ordered)
        wins = sum(record.outcome == "WIN" for record in ordered)
        consecutive = 0
        for record in reversed(ordered):
            if record.outcome == "LOSS":
                consecutive += 1
            else:
                break
        intervals: list[float] = []
        for previous, current in zip(ordered, ordered[1:]):
            try:
                delta = (datetime.fromisoformat(current.created_at.replace("Z", "+00:00")) - datetime.fromisoformat(previous.created_at.replace("Z", "+00:00"))).total_seconds()
            except ValueError:
                continue
            if delta >= 0:
                intervals.append(delta)
        repeated_after_loss = 0
        for previous, current in zip(ordered, ordered[1:]):
            if previous.outcome == "LOSS" and current.is_actionable:
                repeated_after_loss += 1
        return TradingBehaviorSnapshot(
            trades_count=len(ordered), losses=losses, wins=wins,
            consecutive_losses=consecutive,
            avg_seconds_between_trades=(sum(intervals) / len(intervals) if intervals else None),
            rule_breaks=rule_breaks,
            impulsive_entries=impulsive_entries,
            avoided_valid_setups=avoided_valid_setups,
            repeated_entries_after_loss=repeated_after_loss,
            confirmation_requests=confirmation_requests,
            fatigue=fatigue, urge_to_trade=urge_to_trade,
            confidence=confidence, emotional_state=emotional_state,
        )

    def assess_history(self, records: Iterable[DecisionRecord], **context: int | str) -> AdvancedPsychologyAssessment:
        return self.engine.assess(self.snapshot(records, **context))
