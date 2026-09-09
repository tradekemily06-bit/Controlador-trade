from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from execution.ports import ExecutionResult


class RealOutcomeStatus(str, Enum):
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    UNKNOWN = "UNKNOWN"
    INVALID = "INVALID"


@dataclass(frozen=True)
class RealExecutionObservation:
    observation_id: str
    request_id: str
    status: RealOutcomeStatus
    external_id: str | None
    message: str


class RealMonitoringBoundary:
    """Factual observation boundary; never retries or reconciles automatically."""

    def observe(self, *, observation_id: str, request_id: str, result: ExecutionResult | None,
                executor_error: bool = False) -> RealExecutionObservation:
        if not observation_id.strip() or not request_id.strip():
            raise ValueError("observation_id e request_id são obrigatórios.")
        if executor_error or result is None:
            return RealExecutionObservation(observation_id, request_id, RealOutcomeStatus.UNKNOWN, None, "resultado externo incerto; reconciliação explícita necessária")
        if not isinstance(result, ExecutionResult):
            return RealExecutionObservation(observation_id, request_id, RealOutcomeStatus.INVALID, None, "resultado externo inválido")
        status = RealOutcomeStatus.ACCEPTED if result.accepted else RealOutcomeStatus.REJECTED
        return RealExecutionObservation(observation_id, request_id, status, result.external_id, result.message)
