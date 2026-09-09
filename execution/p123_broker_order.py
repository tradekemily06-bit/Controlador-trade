from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math

from core.models import Signal


class BrokerOrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


@dataclass(frozen=True)
class BrokerOrderRequest:
    request_id: str
    symbol: str
    side: BrokerOrderSide
    amount: float
    duration_seconds: int

    def __post_init__(self) -> None:
        if not isinstance(self.request_id, str) or not self.request_id.strip():
            raise ValueError("request_id inválido")
        if not isinstance(self.symbol, str) or not self.symbol.strip():
            raise ValueError("symbol inválido")
        if not isinstance(self.side, BrokerOrderSide):
            raise ValueError("side inválido")
        if isinstance(self.amount, bool) or not isinstance(self.amount, (int, float)) or not math.isfinite(self.amount) or self.amount <= 0:
            raise ValueError("amount inválido")
        if isinstance(self.duration_seconds, bool) or not isinstance(self.duration_seconds, int) or self.duration_seconds <= 0:
            raise ValueError("duration_seconds inválido")


@dataclass(frozen=True)
class BrokerOrderResult:
    accepted: bool
    message: str
    external_id: str | None = None


class BrokerOrderBoundary:
    """Pure broker-order mapping/validation; it never performs network I/O."""

    @staticmethod
    def from_signal(
        *,
        request_id: str,
        symbol: str,
        signal: Signal,
        amount: float,
        duration_seconds: int,
    ) -> BrokerOrderRequest:
        if signal is Signal.AGUARDAR:
            raise ValueError("AGUARDAR não pode gerar ordem")
        if signal is Signal.COMPRA:
            side = BrokerOrderSide.BUY
        elif signal is Signal.VENDA:
            side = BrokerOrderSide.SELL
        else:
            raise ValueError("signal inválido")

        return BrokerOrderRequest(
            request_id=request_id,
            symbol=symbol,
            side=side,
            amount=amount,
            duration_seconds=duration_seconds,
        )

    @staticmethod
    def validate_result(result: BrokerOrderResult) -> BrokerOrderResult:
        if not isinstance(result, BrokerOrderResult):
            raise ValueError("resultado da corretora inválido")
        if not isinstance(result.accepted, bool):
            raise ValueError("accepted inválido")
        if not isinstance(result.message, str) or not result.message.strip():
            raise ValueError("message inválida")
        if result.external_id is not None and (
            not isinstance(result.external_id, str) or not result.external_id.strip()
        ):
            raise ValueError("external_id inválido")
        return result
