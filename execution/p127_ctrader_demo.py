from __future__ import annotations

from typing import Callable, Protocol

from core.global_operational_barrier import GlobalOperationalBarrier

from core.models import Signal
from execution.p123_broker_order import (
    BrokerOrderBoundary,
    BrokerOrderRequest,
    BrokerOrderResult,
)
from execution.ports import ExecutionMode, ExecutionRequest, ExecutionResult


CTRADER_DEMO_ENDPOINT = "demo.ctraderapi.com:5035"


class CTraderDemoTransport(Protocol):
    """External transport supplied by the cTrader adapter integration."""

    def place_market_order(self, order: BrokerOrderRequest) -> BrokerOrderResult:
        ...

    def is_available(self) -> bool:
        ...


class CTraderDemoAdapter:
    """Fail-closed DEMO-only adapter boundary for cTrader Open API."""

    endpoint = CTRADER_DEMO_ENDPOINT

    def __init__(
        self,
        transport: CTraderDemoTransport,
        operational_barrier_provider: Callable[[], GlobalOperationalBarrier] | None = None,
    ) -> None:
        if transport is None:
            raise ValueError("transport obrigatório")
        self._transport = transport
        self._operational_barrier_provider = operational_barrier_provider

    def is_available(self) -> bool:
        return bool(self._transport.is_available())

    def _barrier_error(self) -> str | None:
        if self._operational_barrier_provider is None:
            return "barreira operacional global não configurada; cTrader DEMO bloqueado"
        try:
            barrier = self._operational_barrier_provider()
            if not isinstance(barrier, GlobalOperationalBarrier):
                return "barreira operacional global inválida; cTrader DEMO bloqueado"
            decision = barrier.evaluate()
            if not decision.operationally_allowed:
                return f"barreira operacional bloqueou cTrader DEMO: {decision.reason}"
            return None
        except Exception as exc:
            return f"estado da barreira operacional indisponível: {type(exc).__name__}"

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        if not isinstance(request, ExecutionRequest):
            raise ValueError("request de execução inválido")
        barrier_error = self._barrier_error()
        if barrier_error is not None:
            return ExecutionResult(False, barrier_error)
        if request.mode is not ExecutionMode.DEMO:
            return ExecutionResult(False, "cTrader DEMO adapter rejeita modo diferente de DEMO")
        if request.signal is Signal.AGUARDAR:
            return ExecutionResult(False, "AGUARDAR não gera ordem")
        if not isinstance(request.request_id, str) or not request.request_id.strip():
            return ExecutionResult(False, "request_id obrigatório para execução DEMO")
        if not self.is_available():
            return ExecutionResult(False, "transporte cTrader DEMO indisponível")

        try:
            broker_order = BrokerOrderBoundary.from_signal(
                request_id=request.request_id,
                symbol=request.symbol,
                signal=request.signal,
                amount=request.amount,
                duration_seconds=request.duration_seconds,
            )
            broker_result = self._transport.place_market_order(broker_order)
            validated = BrokerOrderBoundary.validate_result(broker_result)
        except (TypeError, ValueError) as exc:
            return ExecutionResult(False, f"falha de validação cTrader DEMO: {exc}")

        return ExecutionResult(
            accepted=validated.accepted,
            message=validated.message,
            external_id=validated.external_id,
        )
