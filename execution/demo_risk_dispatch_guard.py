from __future__ import annotations

from typing import Callable

from core.demo_risk_state_store import DemoRiskStateUnavailable, DemoRiskStateStore
from execution.ports import ExecutionPort, ExecutionRequest, ExecutionResult


class DemoRiskDispatchGuard:
    """Final DEMO risk gate sharing the authoritative state-store lock."""

    def __init__(self, port: ExecutionPort, *, risk_store: DemoRiskStateStore, risk_fingerprint_provider: Callable[[], str | None]) -> None:
        if port is None:
            raise ValueError("executor é obrigatório")
        if not isinstance(risk_store, DemoRiskStateStore):
            raise ValueError("risk_store inválido")
        if not callable(risk_fingerprint_provider):
            raise ValueError("risk_fingerprint_provider inválido")
        self._port = port
        self._risk_store = risk_store
        self._risk_fingerprint_provider = risk_fingerprint_provider

    def is_available(self) -> bool:
        try:
            return self._risk_store.status()["available"] is True
        except Exception:
            return False

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        expected = request.risk_state_fingerprint
        if expected is None:
            return self._port.execute(request)
        try:
            with self._risk_store.dispatch_lock():
                current = self._risk_fingerprint_provider()
                if current is None:
                    return ExecutionResult(False, "dispatch DEMO bloqueado: estado de risco autoritativo indisponível.")
                if current != expected:
                    return ExecutionResult(False, "dispatch DEMO bloqueado: estado de risco mudou desde a última validação; nova avaliação obrigatória.")
                return self._port.execute(request)
        except (OSError, RuntimeError, DemoRiskStateUnavailable) as exc:
            return ExecutionResult(False, f"dispatch DEMO bloqueado: não foi possível validar atomicamente o estado de risco ({type(exc).__name__}).")
