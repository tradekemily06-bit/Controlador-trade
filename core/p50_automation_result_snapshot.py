from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


from core.p47_automation_closure import AutomationClosure
from core.p48_automation_outcome import AutomationOutcome
from core.p49_outcome_reconciliation import ExternalOutcomeObservation, OutcomeReconciliation, ReconciliationState


@dataclass(frozen=True)
class AutomationResultSnapshot:
    cycle_id: str
    terminal_state: str
    outcome: str
    financial_result: float | None
    reconciliation_state: ReconciliationState
    source: str | None = None
    external_reference: str | None = None
    external_container_id: str | None = None
    external_result_ids: tuple[str, ...] = ()
    observed_at: datetime | None = None


class AutomationResultSnapshotBoundary:
    """Composes factual artifacts without changing their meaning or persisting them."""

    def compose(
        self,
        closure: AutomationClosure,
        outcome: AutomationOutcome,
        reconciliation: OutcomeReconciliation,
        external_observation: ExternalOutcomeObservation | None = None,
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
            if not isinstance(external_observation, ExternalOutcomeObservation):
                raise ValueError("matched result requires the factual external observation")
            if external_observation.cycle_id != closure.cycle_id:
                raise ValueError("external observation cycle_id does not match closure")
            if not (
                external_observation.external_result_ids
                or external_observation.external_reference
                or external_observation.external_container_id
            ):
                raise ValueError("matched result requires external evidence identity")
        elif external_observation is not None and not isinstance(external_observation, ExternalOutcomeObservation):
            raise ValueError("invalid external observation")
        return AutomationResultSnapshot(
            cycle_id=closure.cycle_id,
            terminal_state=closure.terminal_state.value,
            outcome=outcome.outcome,
            financial_result=outcome.financial_result,
            reconciliation_state=reconciliation.state,
            source=external_observation.source if external_observation else None,
            external_reference=external_observation.external_reference if external_observation else None,
            external_container_id=external_observation.external_container_id if external_observation else None,
            external_result_ids=external_observation.external_result_ids if external_observation else (),
            observed_at=external_observation.observed_at if external_observation else None,
        )
