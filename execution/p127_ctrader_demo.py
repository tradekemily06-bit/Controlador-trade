from __future__ import annotations

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

    @staticmethod
    def correlation_for(request: ExecutionRequest) -> str:
        if not isinstance(request, ExecutionRequest) or not isinstance(request.request_id, str) or not request.request_id.strip():
            raise ValueError("request_id obrigatório para correlation cTrader")
        # cTrader clientOrderId is bounded to 50 chars. A deterministic token
        # lets recovery rediscover the order without exposing the raw request id.
        import hashlib
        return "CTD-" + hashlib.sha256(request.request_id.strip().encode("utf-8")).hexdigest()[:32]

    def is_available(self) -> bool:
        ...


class CTraderDemoAdapter:
    """Fail-closed DEMO-only adapter boundary for cTrader Open API."""

    endpoint = CTRADER_DEMO_ENDPOINT
    adapter_id = "ctrader-demo-v1"

    def __init__(self, transport: CTraderDemoTransport) -> None:
        if transport is None:
            raise ValueError("transport obrigatório")
        configured_endpoint = getattr(transport, "endpoint", None)
        if configured_endpoint != CTRADER_DEMO_ENDPOINT:
            raise ValueError("transport cTrader deve estar explicitamente configurado no endpoint DEMO")
        self._transport = transport

    def is_available(self) -> bool:
        return bool(self._transport.is_available())

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        if not isinstance(request, ExecutionRequest):
            return ExecutionResult(False, "request de execução inválido")
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
        except (TypeError, ValueError) as exc:
            return ExecutionResult(False, f"cTrader DEMO rejeitou a requisição antes do despacho: {exc}")

        try:
            broker_result = self._transport.place_market_order(broker_order)
            validated = BrokerOrderBoundary.validate_result(broker_result)
        except (TypeError, ValueError) as exc:
            return ExecutionResult(False, f"cTrader DEMO retornou resposta inválida após despacho potencial: {exc}", uncertain=True)
        except Exception as exc:
            return ExecutionResult(False, f"cTrader DEMO falhou após despacho potencial; resultado incerto: {type(exc).__name__}: {exc}", uncertain=True)

        if validated.accepted and (not isinstance(validated.external_id, str) or not validated.external_id.strip()):
            return ExecutionResult(False, "cTrader DEMO aceitou sem external_id; estado externo incerto.", uncertain=True)

        return ExecutionResult(
            accepted=validated.accepted,
            message=validated.message,
            external_id=validated.external_id,
        )
