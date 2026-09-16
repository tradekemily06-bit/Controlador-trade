"""Read-only MT5 DEMO runtime validation.

Trade operations such as order_check/order_send belong exclusively to the
IC Markets adapter. This helper only inspects terminal/account/symbol state and
therefore cannot become a second broker execution boundary.
"""
from __future__ import annotations

from typing import Any


def run_order_check(mt5: Any, symbol: str = "EURUSD", volume: float = 0.01) -> dict[str, Any]:
    """Validate DEMO account, quote and volume constraints without a trade call."""
    if not mt5.initialize():
        raise RuntimeError("MT5 indisponível")

    try:
        account = mt5.account_info()
        if account is None:
            raise RuntimeError("conta MT5 indisponível")

        demo_mode = getattr(mt5, "ACCOUNT_TRADE_MODE_DEMO", None)
        if demo_mode is None or getattr(account, "trade_mode", None) != demo_mode:
            raise RuntimeError("conta não confirmada como DEMO; validação bloqueada")

        if not mt5.symbol_select(symbol, True):
            raise RuntimeError("símbolo indisponível")

        tick = mt5.symbol_info_tick(symbol)
        if tick is None or not getattr(tick, "ask", 0):
            raise RuntimeError("cotação indisponível")

        info = mt5.symbol_info(symbol)
        if info is None:
            raise RuntimeError("informações do símbolo indisponíveis")

        minimum = float(getattr(info, "volume_min", 0.0))
        maximum = float(getattr(info, "volume_max", 0.0))
        step = float(getattr(info, "volume_step", 0.0))
        if volume < minimum or (maximum > 0 and volume > maximum) or step <= 0:
            raise RuntimeError("volume fora dos limites DEMO")

        return {
            "available": True,
            "demo_account": True,
            "symbol": symbol,
            "volume": float(volume),
            "volume_min": minimum,
            "volume_max": maximum,
            "volume_step": step,
            "order_check_executed": False,
            "order_send_executed": False,
        }
    finally:
        mt5.shutdown()


if __name__ == "__main__":
    import MetaTrader5 as mt5

    result = run_order_check(mt5)
    print(result)
    print("READ_ONLY=True; nenhuma operação de trade foi chamada.")
