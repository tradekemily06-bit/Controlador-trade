from __future__ import annotations

from dataclasses import dataclass

from core.execution_intent import ExecutionIntent
from execution.gateway import ExecutionGateway, GatewayResult


@dataclass(frozen=True)
class ExecutionIntentAdmission:
    """Admits a validated intent through the existing safety gateway only."""

    gateway: ExecutionGateway

    def __post_init__(self) -> None:
        if self.gateway is None:
            raise ValueError("gateway é obrigatório.")

    def admit(self, intent: ExecutionIntent) -> GatewayResult:
        if not isinstance(intent, ExecutionIntent):
            raise ValueError("intent inválida.")
        return self.gateway.execute(
            intent.request_id,
            intent.as_execution_request(),
            timestamp=intent.created_at,
        )
