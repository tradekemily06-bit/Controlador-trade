from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

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

    def execute(self, request_id: str, request: ExecutionRequest, *, expected_timeframe: str | None = None, expected_market_timestamp: datetime | str | None = None, **kwargs) -> GatewayResult:
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
        if expected_timeframe is not None and report.timeframe != expected_timeframe.strip():
            return GatewayResult(
                GatewayStatus.BLOCKED,
                "execução bloqueada: timeframe da decisão não corresponde ao snapshot validado.",
            )
        if self.market_data.validated_snapshot(symbol=request.symbol, timeframe=report.timeframe) is None:
            return GatewayResult(
                GatewayStatus.BLOCKED,
                "execução bloqueada: o snapshot validado não está disponível no runtime.",
            )
        if expected_market_timestamp is not None:\n            snapshot = self.market_data.snapshot\n            if snapshot is None or not snapshot.candles:\n                return GatewayResult(GatewayStatus.BLOCKED, "execução bloqueada: timestamp do mercado não pode ser validado sem candles.")\n            expected = expected_market_timestamp\n            if isinstance(expected, datetime):\n                expected = expected.isoformat()\n            elif isinstance(expected, str):\n                expected = expected.strip()\n            else:\n                return GatewayResult(GatewayStatus.BLOCKED, "execução bloqueada: timestamp da decisão é inválido.")\n            current = snapshot.candles[-1].timestamp.isoformat()\n            if current != expected:\n                return GatewayResult(\n                    GatewayStatus.BLOCKED,\n                    "execução bloqueada: a decisão pertence a um candle fechado diferente do snapshot atualmente validado.",\n                )\n        return self.gateway.execute(request_id, request, **kwargs)
