from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from core.p44_automation_intent_handoff import AutomationIntentHandoffResult


@dataclass(frozen=True)
class AutomationAuditRecord:
    cycle_id: str
    request_id: str
    symbol: str
    direction: str
    mode: str
    intent_created_at: datetime


class AutomationAuditBoundary:
    """Builds a factual, immutable audit artifact without persistence or execution."""

    def record(self, result: AutomationIntentHandoffResult | None) -> AutomationAuditRecord:
        if not isinstance(result, AutomationIntentHandoffResult) or not result.handed_off:
            raise ValueError("approved automation handoff is required")
        if result.handoff is None:
            raise ValueError("approved automation handoff has no artifact")
        intent = result.handoff.intent
        if intent.mode.value != "DEMO":
            raise ValueError("only DEMO intent can be audited")
        return AutomationAuditRecord(
            cycle_id=result.handoff.cycle_id,
            request_id=intent.request_id,
            symbol=intent.symbol,
            direction=intent.signal.value,
            mode=intent.mode.value,
            intent_created_at=intent.created_at,
        )
