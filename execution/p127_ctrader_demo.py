from __future__ import annotations

import math
from typing import Protocol

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
    supports_real_execution = False
    """Fail-closed DEMO-only adapter boundary for cTrader Open API."""

    endpoint = CTRADER_DEMO_ENDPOINT

    def __init__(self, transport: CTraderDemoTransport) -> None:
        if transport is None:
            raise ValueError("transport obrigatório")
        self._transport = transport

    def is_available(self) -> bool:
        try:
            available = self._transport.is_available()
        except Exception:
            return False
        if type(available) is not bool:
            return False
        return available

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        if type(request) is not ExecutionRequest:
            return ExecutionResult(False, "request de execução inválido")
        if request.mode is not ExecutionMode.DEMO:
            return ExecutionResult(False, "cTrader DEMO adapter rejeita modo diferente de DEMO")
        if request.signal is Signal.AGUARDAR:
            return ExecutionResult(False, "AGUARDAR não gera ordem")
        if not isinstance(request.symbol, str) or not request.symbol.strip():
            return ExecutionResult(False, "símbolo inválido")
        if (
            not isinstance(request.amount, (int, float))
            or isinstance(request.amount, bool)
            or not math.isfinite(float(request.amount))
            or request.amount <= 0
        ):
            return ExecutionResult(False, "amount inválido")
        if (
            not isinstance(request.duration_seconds, int)
            or isinstance(request.duration_seconds, bool)
            or request.duration_seconds <= 0
        ):
            return ExecutionResult(False, "duration_seconds inválido")
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
        except Exception as exc:
            return ExecutionResult(False, f"falha cTrader DEMO: {exc}")

        if not isinstance(validated, BrokerOrderResult):
            return ExecutionResult(False, "resultado cTrader DEMO inválido")
        if type(validated.accepted) is not bool:
            return ExecutionResult(False, "accepted cTrader DEMO inválido")
        if not isinstance(validated.message, str) or not validated.message.strip():
            return ExecutionResult(False, "message cTrader DEMO inválida")
        if validated.external_id is not None and (
            not isinstance(validated.external_id, str) or not validated.external_id.strip()
        ):
            return ExecutionResult(False, "external_id cTrader DEMO inválido")

        return ExecutionResult(
            accepted=validated.accepted,
            message=validated.message,
            external_id=validated.external_id,
        )
