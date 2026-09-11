"""Read-only MT5 DEMO order validation.

This module intentionally calls order_check() but never calls order_send().
It is for the first live-terminal validation of the IC Markets DEMO boundary.
"""
from __future__ import annotations

from typing import Any


def run_order_check(mt5: Any, symbol: str = "EURUSD", volume: float = 0.01) -> Any:
    """Validate a minimum-volume market BUY without submitting it."""
    if not mt5.initialize():
        raise RuntimeError(f"MT5 indisponível: {mt5.last_error()}")

    try:
        account = mt5.account_info()
        if account is None:
            raise RuntimeError("conta MT5 indisponível")

        demo_mode = getattr(mt5, "ACCOUNT_TRADE_MODE_DEMO", None)
        if demo_mode is None or getattr(account, "trade_mode", None) != demo_mode:
            raise RuntimeError("conta não confirmada como DEMO; order_check bloqueado")

        if not mt5.symbol_select(symbol, True):
            raise RuntimeError(f"símbolo indisponível: {symbol}")

        tick = mt5.symbol_info_tick(symbol)
        if tick is None or not getattr(tick, "ask", 0):
            raise RuntimeError(f"cotação indisponível: {symbol}")

        info = mt5.symbol_info(symbol)
        if info is None:
            raise RuntimeError(f"informações do símbolo indisponíveis: {symbol}")

        minimum = float(getattr(info, "volume_min", 0.0))
        step = float(getattr(info, "volume_step", 0.0))
        if volume < minimum or step <= 0:
            raise RuntimeError(
                f"volume inválido: volume={volume}, mínimo={minimum}, step={step}"
            )

        payload = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": float(volume),
            "type": mt5.ORDER_TYPE_BUY,
            "price": tick.ask,
            "deviation": 20,
            "magic": 2609001,
            "comment": "ControladorTrading-DEMO-CHECK",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        return mt5.order_check(payload)
    finally:
        mt5.shutdown()


if __name__ == "__main__":
    import MetaTrader5 as mt5

    result = run_order_check(mt5)
    print(result)
    print("READ_ONLY=True; order_send NÃO foi chamado.")
