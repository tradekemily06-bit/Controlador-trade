from __future__ import annotations

from dataclasses import dataclass

from core.market_data_runtime_state import MarketDataRuntimeState
from execution.gateway import ExecutionGateway, GatewayResult
from execution.ports import ExecutionRequest


@dataclass(frozen=True)
class MarketDataExecutionGuard:
    """Compatibility boundary that delegates market-data admission to the gateway.

    The gateway is the single authority for validated market-data checks. This
    wrapper keeps the existing integration surface without duplicating safety
    semantics.
    """

    market_data: MarketDataRuntimeState
    gateway: ExecutionGateway

    def execute(self, request_id: str, request: ExecutionRequest, **kwargs) -> GatewayResult:
        return self.gateway.execute(request_id, request, **kwargs)
