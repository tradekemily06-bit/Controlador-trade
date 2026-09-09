from __future__ import annotations

from dataclasses import dataclass

from core.p73_next_cycle_admission import AdmissionStatus, NextCycleAdmission


@dataclass(frozen=True)
class NextCycleHandoff:
    handoff_id: str
    archive_id: str
    proposal_id: str
    application_id: str
    observation_id: str
    context: str
    real_execution_allowed: bool = False


class NextCycleHandoffBoundary:
    def create(
        self,
        admission: NextCycleAdmission | None,
        *,
        handoff_id: str,
        context: str,
    ) -> NextCycleHandoff:
        if not isinstance(admission, NextCycleAdmission):
            raise ValueError("invalid next-cycle admission")
        if admission.status is not AdmissionStatus.ADMITTED:
            raise ValueError("next-cycle admission is blocked")
        if not isinstance(handoff_id, str) or not handoff_id.strip():
            raise ValueError("handoff_id is required")
        if not isinstance(context, str) or not context.strip():
            raise ValueError("handoff context is required")
        return NextCycleHandoff(
            handoff_id=handoff_id.strip(),
            archive_id=admission.archive_id,
            proposal_id=admission.proposal_id,
            application_id=admission.application_id,
            observation_id=admission.observation_id,
            context=context.strip(),
        )
