from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol, TYPE_CHECKING

from execution.ports import ExecutionMode, ExecutionRequest, ExecutionResult

if TYPE_CHECKING:
    from core.global_operational_barrier import GlobalOperationalBarrier


@dataclass(frozen=True)
class BridgeHealth:
    available: bool
    demo_account: bool
    message: str


class RemoteMT5Bridge(Protocol):
    """Transport boundary for a cloud-hosted MT5 terminal."""

    def health(self) -> BridgeHealth: ...

    def execute_demo(self, request: ExecutionRequest) -> ExecutionResult: ...


class SafeRemoteMT5Executor:
    """Fail-closed facade for a remote MT5 bridge.

    This class is an executor boundary, not an operational gateway.  It may be
    called by the DEMO execution gateway, but it must never become an alternate
    route around the ecosystem-wide safety barrier.  A missing barrier provider
    therefore blocks dispatch instead of treating the bridge health check as
    sufficient authorization.
    """

    def __init__(
        self,
        bridge: RemoteMT5Bridge,
        operational_barrier_provider: Callable[[], GlobalOperationalBarrier] | None = None,
    ) -> None:
        if bridge is None:
            raise ValueError("bridge obrigatório")
        if operational_barrier_provider is not None and not callable(operational_barrier_provider):
            raise ValueError("operational_barrier_provider inválido")
        self._bridge = bridge
        self._operational_barrier_provider = operational_barrier_provider

    def _barrier_error(self) -> str | None:
        provider = self._operational_barrier_provider
        if provider is None:
            return "barreira operacional global não configurada; ponte MT5 bloqueada"
        try:
            barrier = provider()
            if not isinstance(barrier, GlobalOperationalBarrier):
                return "provedor da barreira operacional global retornou um objeto inválido"
            decision = barrier.evaluate()
            if not decision.operationally_allowed:
                return f"ponte MT5 bloqueada pela barreira operacional global: {decision.reason}"
            return None
        except Exception as exc:
            return f"estado da barreira operacional global indisponível: {type(exc).__name__}"

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        if not isinstance(request, ExecutionRequest):
            return ExecutionResult(False, "request de execução inválido.")
        if request.mode is not ExecutionMode.DEMO:
            return ExecutionResult(False, "ponte MT5 remota aceita somente DEMO.")

        barrier_error = self._barrier_error()
        if barrier_error is not None:
            return ExecutionResult(False, barrier_error)

        try:
            health = self._bridge.health()
        except Exception as exc:
            return ExecutionResult(False, f"estado da ponte MT5 indisponível: {type(exc).__name__}")
        if not health.available or not health.demo_account:
            return ExecutionResult(False, f"ponte MT5 bloqueada: {health.message}")

        return self._bridge.execute_demo(request)
