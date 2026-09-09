from __future__ import annotations

from dataclasses import dataclass

from core.p75_handoff_validation import HandoffValidation, HandoffValidationStatus


@dataclass(frozen=True)
class NextCycleContext:
    context_id: str
    handoff_id: str
    archive_id: str
    proposal_id: str
    application_id: str
    observation_id: str
    context: str


class NextCycleContextBoundary:
    def create(
        self,
        validation: HandoffValidation | None,
        *,
        context_id: str,
        context: str,
    ) -> NextCycleContext:
        if not isinstance(validation, HandoffValidation):
            raise ValueError("invalid handoff validation")
        if validation.status is not HandoffValidationStatus.VERIFIED:
            raise ValueError("handoff is not verified")
        if not isinstance(context_id, str) or not context_id.strip():
            raise ValueError("context_id is required")
        if not isinstance(context, str) or not context.strip():
            raise ValueError("context is required")
        return NextCycleContext(
            context_id=context_id.strip(),
            handoff_id=validation.handoff_id,
            archive_id=validation.archive_id,
            proposal_id=validation.proposal_id,
            application_id=validation.application_id,
            observation_id=validation.observation_id,
            context=context.strip(),
        )
