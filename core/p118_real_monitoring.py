from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
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
    observed_at: datetime
    source: str

    def __post_init__(self) -> None:
        if not isinstance(self.observation_id, str) or not self.observation_id.strip():
            raise ValueError("observation_id é obrigatório.")
        if not isinstance(self.request_id, str) or not self.request_id.strip():
            raise ValueError("request_id é obrigatório.")
        if not isinstance(self.status, RealOutcomeStatus):
            raise ValueError("status da observação inválido.")
        if self.external_id is not None and (not isinstance(self.external_id, str) or not self.external_id.strip()):
            raise ValueError("external_id da observação inválido.")
        if not isinstance(self.message, str) or not self.message.strip():
            raise ValueError("message da observação é obrigatório.")
        if not isinstance(self.observed_at, datetime):
            raise ValueError("timestamp da observação inválido.")
        if self.observed_at.tzinfo is None:
            raise ValueError("timestamp da observação deve conter timezone.")
        if not isinstance(self.source, str) or not self.source.strip():
            raise ValueError("source da observação é obrigatório.")


class RealMonitoringBoundary:
    """Factual observation boundary; never retries or reconciles automatically.

    An accepted observation without an external reference is deliberately
    downgraded to UNKNOWN. Monitoring evidence is descriptive, not an
    authorization capability.
    """

    def observe(
        self,
        *,
        observation_id: str,
        request_id: str,
        result: ExecutionResult | None,
        executor_error: bool = False,
        observed_at: datetime | None = None,
        source: str = "real_execution_gateway",
    ) -> RealExecutionObservation:
        if not observation_id.strip() or not request_id.strip():
            raise ValueError("observation_id e request_id são obrigatórios.")
        timestamp = observed_at or datetime.now(timezone.utc)
        if timestamp.tzinfo is None:
            raise ValueError("observed_at deve conter timezone.")
        if not isinstance(source, str) or not source.strip():
            raise ValueError("source é obrigatório.")

        if executor_error or result is None:
            return RealExecutionObservation(
                observation_id, request_id, RealOutcomeStatus.UNKNOWN, None,
                "resultado externo incerto; reconciliação explícita necessária",
                timestamp, source.strip(),
            )
        if not isinstance(result, ExecutionResult):
            return RealExecutionObservation(
                observation_id, request_id, RealOutcomeStatus.INVALID, None,
                "resultado externo inválido", timestamp, source.strip(),
            )

        if result.accepted and (not isinstance(result.external_id, str) or not result.external_id.strip()):
            return RealExecutionObservation(
                observation_id, request_id, RealOutcomeStatus.UNKNOWN, None,
                "aceite sem external_id não constitui evidência confirmada; reconciliação explícita necessária",
                timestamp, source.strip(),
            )

        status = RealOutcomeStatus.ACCEPTED if result.accepted else RealOutcomeStatus.REJECTED
        return RealExecutionObservation(
            observation_id, request_id, status, result.external_id, result.message,
            timestamp, source.strip(),
        )
