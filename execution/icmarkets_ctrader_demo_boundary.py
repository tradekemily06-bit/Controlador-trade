from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from execution.ports import ExecutionMode, ExecutionRequest, ExecutionResult


ICMARKETS_CTRADER_DEMO_SERVER = "cTrader Demo"


class ICMarketsDemoStatus(str, Enum):
    READY = "READY"
    NOT_CONFIGURED = "NOT_CONFIGURED"
    API_PENDING_APPROVAL = "API_PENDING_APPROVAL"


@dataclass(frozen=True)
class ICMarketsDemoConfig:
    """Non-secret configuration for the existing IC Markets DEMO account.

    Account credentials/tokens are deliberately not stored here or in source
    control. This boundary can be completed once cTrader Open API access is
    approved, without changing the broker-agnostic execution gateway.
    """

    account_id: int
    server: str = ICMARKETS_CTRADER_DEMO_SERVER
    mode: ExecutionMode = ExecutionMode.DEMO

    def __post_init__(self) -> None:
        if self.account_id <= 0:
            raise ValueError("account_id inválido")
        if self.server != ICMARKETS_CTRADER_DEMO_SERVER:
            raise ValueError("servidor IC Markets cTrader DEMO inválido")
        if self.mode is not ExecutionMode.DEMO:
            raise ValueError("esta integração aceita somente DEMO")


class ICMarketsCTraderDemoBoundary:
    """Fail-closed boundary waiting for approved cTrader Open API access."""

    def __init__(self, config: ICMarketsDemoConfig | None = None) -> None:
        self._config = config

    @property
    def status(self) -> ICMarketsDemoStatus:
        if self._config is None:
            return ICMarketsDemoStatus.NOT_CONFIGURED
        return ICMarketsDemoStatus.API_PENDING_APPROVAL

    def is_available(self) -> bool:
        return self.status is ICMarketsDemoStatus.READY

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        if not isinstance(request, ExecutionRequest):
            return ExecutionResult(False, "requisição de execução inválida")
        if request.mode is not ExecutionMode.DEMO:
            return ExecutionResult(False, "IC Markets DEMO aceita somente DEMO")
        if not request.request_id:
            return ExecutionResult(False, "request_id obrigatório")
        if not self.is_available():
            return ExecutionResult(
                False,
                "IC Markets cTrader DEMO indisponível até a aprovação da Open API; nenhuma ordem foi enviada.",
            )
        return ExecutionResult(False, "transporte IC Markets cTrader DEMO ainda não conectado")
