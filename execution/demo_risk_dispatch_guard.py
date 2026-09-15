from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Callable

from core.demo_risk_state_store import DemoRiskStateUnavailable, DemoRiskStateStore
from execution.ports import ExecutionPort, ExecutionRequest, ExecutionResult


class DemoRiskDispatchGuard:
    """Final local DEMO risk gate shared with the authoritative state store.

    The execution gateway already performs an early and a final fingerprint
    check. This wrapper closes the remaining local race by taking the same
    cross-process store lock, revalidating the fingerprint, and only then
    invoking the DEMO executor. A state publisher using the same store cannot
    change risk state between that validation and the local executor call.

    This is intentionally a DEMO/local atomicity primitive. It does not claim
    that a remote broker can be made atomic by a local filesystem lock.
    """

    def __init__(
        self,
        executor: ExecutionPort,
        *,
        risk_store: DemoRiskStateStore,
        risk_fingerprint_provider: Callable[[], str | None],
    ) -> None:
        if executor is None:
            raise ValueError("executor é obrigatório")
        if not isinstance(risk_store, DemoRiskStateStore):
            raise ValueError("risk_store inválido")
        if not callable(risk_fingerprint_provider):
            raise ValueError("risk_fingerprint_provider inválido")
        self._executor = executor
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
            return self._executor.execute(request)

        try:
            with self._risk_store.dispatch_lock():
                current = self._risk_fingerprint_provider()
                if current is None:
                    return ExecutionResult(
                        accepted=False,
                        message="dispatch DEMO bloqueado: estado de risco autoritativo indisponível.",
                    )
                if current != expected:
                    return ExecutionResult(
                        accepted=False,
                        message="dispatch DEMO bloqueado: estado de risco mudou desde a última validação; nova avaliação obrigatória.",
                    )
                return self._executor.execute(request)
        except (OSError, RuntimeError, DemoRiskStateUnavailable) as exc:
            return ExecutionResult(
                accepted=False,
                message=f"dispatch DEMO bloqueado: não foi possível validar atomicamente o estado de risco ({type(exc).__name__}).",
            )
