from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Protocol

from core.models import Signal
from execution.ports import ExecutionMode, ExecutionRequest, ExecutionResult


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
    """Fail-closed execution facade for a remote MT5 bridge."""

    def __init__(self, bridge: RemoteMT5Bridge) -> None:
        if bridge is None:
            raise ValueError("bridge obrigatório")
        self._bridge = bridge

    @staticmethod
    def _validate(request: ExecutionRequest) -> str | None:
        if not isinstance(request, ExecutionRequest):
            return "requisição de execução inválida."
        if request.mode is not ExecutionMode.DEMO:
            return "ponte MT5 remota aceita somente DEMO."
        if request.signal not in (Signal.COMPRA, Signal.VENDA):
            return "AGUARDAR não pode gerar ordem."
        if not isinstance(request.request_id, str) or not request.request_id.strip():
            return "request_id obrigatório."
        if not isinstance(request.symbol, str) or not request.symbol.strip():
            return "símbolo obrigatório."
        if not isinstance(request.amount, (int, float)) or isinstance(request.amount, bool):
            return "amount inválido."
        if not math.isfinite(float(request.amount)) or request.amount <= 0:
            return "amount deve ser positivo e finito."
        if not isinstance(request.duration_seconds, int) or isinstance(request.duration_seconds, bool) or request.duration_seconds <= 0:
            return "duração inválida."
        return None

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        error = self._validate(request)
        if error is not None:
            return ExecutionResult(False, error)

        try:
            health = self._bridge.health()
        except Exception as exc:
            return ExecutionResult(False, f"ponte MT5 bloqueada: health indisponível ({type(exc).__name__}).")

        if not isinstance(health, BridgeHealth):
            return ExecutionResult(False, "ponte MT5 bloqueada: health inválido.")
        if not health.available or not health.demo_account:
            return ExecutionResult(False, f"ponte MT5 bloqueada: {health.message}")

        try:
            result = self._bridge.execute_demo(request)
        except Exception as exc:
            return ExecutionResult(False, f"ponte MT5 falhou; execução não confirmada: {type(exc).__name__}.")

        if not isinstance(result, ExecutionResult):
            return ExecutionResult(False, "ponte MT5 retornou resultado inválido.")

        if result.accepted and (not isinstance(result.external_id, str) or not result.external_id.strip()):
            return ExecutionResult(False, "ponte MT5 aceitou sem external_id; confirmação bloqueada.")

        return result
