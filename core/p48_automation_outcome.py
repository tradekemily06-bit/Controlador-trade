from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from core.p47_automation_closure import AutomationClosure, AutomationLifecycleState


@dataclass(frozen=True)
class AutomationOutcome:
    cycle_id: str
    terminal_state: AutomationLifecycleState
    observed_at: datetime
    outcome: Literal["WIN", "LOSS", "DRAW", "UNKNOWN"]
    financial_result: float | None
    source: str = "UNKNOWN"
    closed_at: datetime | None = None


class AutomationOutcomeBoundary:
    """Records an explicitly supplied observation; it never derives an outcome."""

    def record(
        self,
        closure: AutomationClosure,
        *,
        observed_at: datetime,
        outcome: Literal["WIN", "LOSS", "DRAW", "UNKNOWN"],
        financial_result: float | None = None,
        source: str = "UNKNOWN",
        closed_at: datetime | None = None,
    ) -> AutomationOutcome:
        if not isinstance(closure, AutomationClosure):
            raise ValueError("invalid automation closure")
        if not isinstance(observed_at, datetime) or observed_at.tzinfo is None or observed_at.utcoffset() is None:
            raise ValueError("observed_at must be timezone-aware")
        if observed_at < closure.closed_at:
            raise ValueError("observed_at cannot precede automation closure")
        if closed_at is not None:
            if not isinstance(closed_at, datetime) or closed_at.tzinfo is None or closed_at.utcoffset() is None:
                raise ValueError("closed_at must be timezone-aware or None")
            if closed_at > observed_at:
                raise ValueError("closed_at cannot be later than observed_at")
        if not isinstance(closure.cycle_id, str) or not closure.cycle_id.strip():
            raise ValueError("cycle_id is required")
        if outcome not in {"WIN", "LOSS", "DRAW", "UNKNOWN"}:
            raise ValueError("invalid automation outcome")
        if not isinstance(source, str) or not source.strip():
            raise ValueError("source is required")
        if financial_result is not None:
            if isinstance(financial_result, bool) or not isinstance(financial_result, (int, float)):
                raise ValueError("financial_result must be numeric or None")
            if financial_result != financial_result or financial_result in {float("inf"), float("-inf")}:
                raise ValueError("financial_result must be finite")
            financial_result = float(financial_result)
        if outcome == "UNKNOWN" and financial_result is not None:
            raise ValueError("UNKNOWN outcome cannot carry a financial result")
        if closure.terminal_state is AutomationLifecycleState.BLOCKED and outcome != "UNKNOWN":
            raise ValueError("blocked cycles can only receive UNKNOWN outcome")
        return AutomationOutcome(
            cycle_id=closure.cycle_id,
            terminal_state=closure.terminal_state,
            observed_at=observed_at,
            outcome=outcome,
            financial_result=financial_result,
            source=source.strip(),
            closed_at=closed_at,
        )
