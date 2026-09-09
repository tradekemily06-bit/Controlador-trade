from __future__ import annotations

from dataclasses import dataclass

from core.p64_adaptation_activation import AdaptationActivation


@dataclass(frozen=True)
class AdaptationObservation:
    proposal_id: str
    application_id: str
    activation_id: str
    observation_id: str
    sample_size: int
    observation: str


class AdaptationObservationBoundary:
    def record(
        self,
        activation: AdaptationActivation | None,
        *,
        observation_id: str,
        sample_size: int,
        observation: str,
    ) -> AdaptationObservation:
        if not isinstance(activation, AdaptationActivation):
            raise ValueError("invalid adaptation activation")
        if not isinstance(observation_id, str) or not observation_id.strip():
            raise ValueError("observation_id is required")
        if not isinstance(sample_size, int) or isinstance(sample_size, bool) or sample_size <= 0:
            raise ValueError("sample_size must be a positive integer")
        if not isinstance(observation, str) or not observation.strip():
            raise ValueError("observation is required")
        return AdaptationObservation(
            proposal_id=activation.proposal_id,
            application_id=activation.application_id,
            activation_id=activation.activation_id,
            observation_id=observation_id.strip(),
            sample_size=sample_size,
            observation=observation.strip(),
        )
