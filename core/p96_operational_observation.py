from __future__ import annotations

from dataclasses import dataclass

from core.p95_controlled_operational_closure import ControlledOperationalClosure


@dataclass(frozen=True)
class OperationalObservation:
    observation_id: str
    closure_id: str
    admission_id: str
    disposition_id: str
    evaluation_id: str
    use_id: str
    knowledge_id: str
    hypothesis_id: str
    scope: str
    sample_size: int
    observation: str
    real_execution_allowed: bool = False


class OperationalObservationBoundary:
    def record(
        self,
        closure: ControlledOperationalClosure | None,
        *,
        observation_id: str,
        sample_size: int,
        observation: str,
    ) -> OperationalObservation:
        if not isinstance(closure, ControlledOperationalClosure):
            raise ValueError("invalid controlled operational closure")
        if closure.status != "CLOSED":
            raise ValueError("operational closure is not closed")
        if not isinstance(observation_id, str) or not observation_id.strip():
            raise ValueError("observation_id is required")
        if not isinstance(sample_size, int) or isinstance(sample_size, bool) or sample_size <= 0:
            raise ValueError("sample_size must be positive")
        if not isinstance(observation, str) or not observation.strip():
            raise ValueError("observation is required")
        return OperationalObservation(
            observation_id=observation_id.strip(),
            closure_id=closure.closure_id,
            admission_id=closure.admission_id,
            disposition_id=closure.disposition_id,
            evaluation_id=closure.evaluation_id,
            use_id=closure.use_id,
            knowledge_id=closure.knowledge_id,
            hypothesis_id=closure.hypothesis_id,
            scope=closure.scope,
            sample_size=sample_size,
            observation=observation.strip(),
        )
