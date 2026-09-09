from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from execution.p121_external_order_reconciliation import ExternalOrderStatus
from execution.p123_broker_order import BrokerOrderRequest, BrokerOrderResult


class SandboxScenario(str, Enum):
    ACCEPT = "ACCEPT"
    REJECT = "REJECT"
    UNKNOWN = "UNKNOWN"
    DISCONNECTED = "DISCONNECTED"


@dataclass(frozen=True)
class SandboxValidationResult:
    scenario: SandboxScenario
    accepted: bool
    external_id: str | None
    external_status: ExternalOrderStatus
    duplicate_blocked: bool
    message: str


class SandboxBroker:
    """Deterministic in-memory broker simulator; never reaches a real broker."""

    def __init__(self) -> None:
        self._requests: dict[str, BrokerOrderResult] = {}
        self._external: dict[str, ExternalOrderStatus] = {}
        self._sequence = 0

    def execute(self, request: BrokerOrderRequest, scenario: SandboxScenario) -> BrokerOrderResult:
        if request.request_id in self._requests:
            return BrokerOrderResult(False, "request_id já utilizado; nova submissão bloqueada")

        if scenario is SandboxScenario.ACCEPT:
            self._sequence += 1
            external_id = f"sandbox-{self._sequence}"
            result = BrokerOrderResult(True, "accepted", external_id)
            self._requests[request.request_id] = result
            self._external[external_id] = ExternalOrderStatus.EXECUTED
            return result

        if scenario is SandboxScenario.REJECT:
            result = BrokerOrderResult(False, "rejected")
            self._requests[request.request_id] = result
            return result

        if scenario is SandboxScenario.UNKNOWN:
            result = BrokerOrderResult(True, "ambiguous", None)
            self._requests[request.request_id] = result
            return result

        result = BrokerOrderResult(False, "disconnected")
        self._requests[request.request_id] = result
        return result

    def query(self, external_id: str) -> ExternalOrderStatus:
        return self._external.get(external_id, ExternalOrderStatus.UNKNOWN)


class SandboxValidationBoundary:
    """Exercises P123/P120/P121 invariants without network or REAL execution."""

    def __init__(self, broker: SandboxBroker | None = None) -> None:
        self.broker = broker or SandboxBroker()

    def run(self, request: BrokerOrderRequest, scenario: SandboxScenario) -> SandboxValidationResult:
        first = self.broker.execute(request, scenario)
        duplicate_blocked = False
        if scenario is SandboxScenario.ACCEPT:
            duplicate = self.broker.execute(request, SandboxScenario.ACCEPT)
            duplicate_blocked = not duplicate.accepted

        if first.accepted and first.external_id:
            status = self.broker.query(first.external_id)
            return SandboxValidationResult(
                scenario, True, first.external_id, status, duplicate_blocked, first.message
            )

        if first.accepted and first.external_id is None:
            return SandboxValidationResult(
                scenario, True, None, ExternalOrderStatus.UNKNOWN, duplicate_blocked, first.message
            )

        return SandboxValidationResult(
            scenario, False, None, ExternalOrderStatus.NOT_EXECUTED, duplicate_blocked, first.message
        )
