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
    holds a HEALTHY market-data report for the same symbol.
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
        if self.market_data.validated_snapshot_for_symbol(symbol=request.symbol) is None:
            return GatewayResult(
                GatewayStatus.BLOCKED,
                "execução bloqueada: o snapshot validado não está disponível no runtime.",
            )
        return self.gateway.execute(request_id, request, **kwargs)
