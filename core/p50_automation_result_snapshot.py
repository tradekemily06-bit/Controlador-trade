from __future__ import annotations

from dataclasses import dataclass

from core.p47_automation_closure import AutomationClosure
from core.p48_automation_outcome import AutomationOutcome
from core.p49_outcome_reconciliation import OutcomeReconciliation, ReconciliationState


@dataclass(frozen=True)
class AutomationResultSnapshot:
    cycle_id: str
    terminal_state: str
    outcome: str
    financial_result: float | None
    reconciliation_state: ReconciliationState


class AutomationResultSnapshotBoundary:
    """Composes factual artifacts without changing their meaning or persisting them."""

    def compose(
        self,
        closure: AutomationClosure,
        outcome: AutomationOutcome,
        reconciliation: OutcomeReconciliation,
    ) -> AutomationResultSnapshot:
        if not isinstance(closure, AutomationClosure):
            raise ValueError("invalid automation closure")
        if not isinstance(outcome, AutomationOutcome):
            raise ValueError("invalid automation outcome")
        if not isinstance(reconciliation, OutcomeReconciliation):
            raise ValueError("invalid outcome reconciliation")
        if not closure.cycle_id.strip() or outcome.cycle_id != closure.cycle_id or reconciliation.cycle_id != closure.cycle_id:
            raise ValueError("automation artifacts must reference the same cycle")
        if outcome.terminal_state is not closure.terminal_state:
            raise ValueError("outcome terminal state does not match closure")
        if reconciliation.state is ReconciliationState.MATCHED:
            if outcome.outcome == "UNKNOWN":
                raise ValueError("UNKNOWN outcome cannot be presented as matched")
        return AutomationResultSnapshot(
            cycle_id=closure.cycle_id,
            terminal_state=closure.terminal_state.value,
            outcome=outcome.outcome,
            financial_result=outcome.financial_result,
            reconciliation_state=reconciliation.state,
        )
