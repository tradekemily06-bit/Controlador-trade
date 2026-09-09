from __future__ import annotations

from dataclasses import dataclass

from core.p62_controlled_adaptation import AppliedAdaptation


@dataclass(frozen=True)
class AdaptationActivation:
    proposal_id: str
    application_id: str
    activation_id: str
    context: str
    real_execution_allowed: bool = False


class AdaptationActivationBoundary:
    def activate(
        self,
        application: AppliedAdaptation | None,
        *,
        activation_id: str,
        context: str,
    ) -> AdaptationActivation:
        if not isinstance(application, AppliedAdaptation):
            raise ValueError("invalid applied adaptation")
        if not isinstance(activation_id, str) or not activation_id.strip():
            raise ValueError("activation_id is required")
        if not isinstance(context, str) or not context.strip():
            raise ValueError("activation context is required")
        return AdaptationActivation(
            proposal_id=application.proposal_id,
            application_id=application.application_id,
            activation_id=activation_id.strip(),
            context=context.strip(),
        )
