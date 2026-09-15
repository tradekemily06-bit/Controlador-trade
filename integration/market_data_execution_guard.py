from __future__ import annotations

from dataclasses import dataclass

from core.market_data_runtime_state import MarketDataRuntimeState
from execution.gateway import ExecutionGateway, GatewayResult, GatewayStatus
from execution.ports import ExecutionRequest


@dataclass(frozen=True)
class MarketDataExecutionGuard:
    """Provider-neutral bridge from validated market data to the execution gateway.

    This boundary never fetches data and never selects a broker. It only permits
    an already-created execution request to reach the gateway when the runtime
    holds a HEALTHY market-data report for the same symbol *and* the request
    carries the exact market-data identity that was validated. The gateway can
    then re-check that identity immediately before dispatch, closing the
    check-to-dispatch gap instead of treating a one-time health check as proof
    that the market context is still the same.
    """

    market_data: MarketDataRuntimeState
    gateway: ExecutionGateway

    def execute(self, request_id: str, request: ExecutionRequest, **kwargs) -> GatewayResult:
        report = self.market_data.report
        if report is None:
            return GatewayResult(
                GatewayStatus.BLOCKED,
                "execução bloqueada: nenhum snapshot de mercado validado está disponível.",
            )
        if not report.safe_for_analysis:
            return GatewayResult(
                GatewayStatus.BLOCKED,
                f"execução bloqueada: dados de mercado não estão HEALTHY ({report.health.value}).",
            )
        if report.symbol != request.symbol:
            return GatewayResult(
                GatewayStatus.BLOCKED,
                "execução bloqueada: símbolo da requisição não corresponde ao snapshot validado.",
            )
        if not isinstance(report.fingerprint, str) or len(report.fingerprint) != 64:
            return GatewayResult(
                GatewayStatus.BLOCKED,
                "execução bloqueada: identidade do snapshot de mercado não está disponível.",
            )
        if request.market_data_fingerprint != report.fingerprint:
            return GatewayResult(
                GatewayStatus.BLOCKED,
                "execução bloqueada: identidade de mercado da requisição não corresponde ao snapshot validado.",
            )
        return self.gateway.execute(request_id, request, **kwargs)
