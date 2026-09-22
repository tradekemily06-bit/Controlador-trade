from __future__ import annotations

from dataclasses import dataclass

from core.models import Signal
from execution.ports import ExecutionMode, ExecutionRequest


@dataclass(frozen=True)
class DemoCloseIntent:
    """Non-dispatching description of a future DEMO close operation."""

    request_id: str
    position_ticket: int
    symbol: str
    volume: float
    signal: Signal = Signal.VENDA


def build_close_intent(*, request_id: str, position_ticket: int, symbol: str, volume: float) -> DemoCloseIntent:
    if not isinstance(request_id, str) or not request_id.strip():
        raise ValueError("request_id obrigatório.")
    if not isinstance(position_ticket, int) or position_ticket <= 0:
        raise ValueError("position_ticket inválido.")
    if not isinstance(symbol, str) or not symbol.strip():
        raise ValueError("symbol inválido.")
    if not isinstance(volume, (int, float)) or volume <= 0:
        raise ValueError("volume inválido.")
    return DemoCloseIntent(request_id, position_ticket, symbol.strip(), float(volume))


def as_execution_request(intent: DemoCloseIntent) -> ExecutionRequest:
    """Convert only to the governed request contract; never sends to MT5."""
    return ExecutionRequest(
        symbol=intent.symbol,
        signal=intent.signal,
        amount=intent.volume,
        duration_seconds=1,
        mode=ExecutionMode.DEMO,
        request_id=intent.request_id,
    )


def main() -> None:
    print("CLOSE DEMO DIRECT DISPATCH DISABLED.")
    print("A posição deve ser fechada somente pelo fluxo de execução governado.")
    print("Este módulo não inicializa MT5 e não chama order_send().")


if __name__ == "__main__":
    main()
