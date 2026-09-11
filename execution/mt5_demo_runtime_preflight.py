from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class MT5RuntimePreflight:
    available: bool
    demo: bool
    symbol: str
    bid: float | None
    ask: float | None
    volume_min: float | None
    volume_step: float | None
    message: str


def run_preflight(mt5: Any, symbol: str = "EURUSD") -> MT5RuntimePreflight:
    """Read-only MT5 runtime validation; never calls order_check/order_send."""
    try:
        if not mt5.initialize():
            return MT5RuntimePreflight(False, False, symbol, None, None, None, None, f"MT5 indisponível: {mt5.last_error()}")

        account = mt5.account_info()
        demo_mode = getattr(mt5, "ACCOUNT_TRADE_MODE_DEMO", None)
        demo = account is not None and demo_mode is not None and getattr(account, "trade_mode", None) == demo_mode
        if not demo:
            return MT5RuntimePreflight(False, False, symbol, None, None, None, None, "conta MT5 não confirmada como DEMO")

        if not mt5.symbol_select(symbol, True):
            return MT5RuntimePreflight(False, True, symbol, None, None, None, None, f"símbolo não disponível: {symbol}")

        info = mt5.symbol_info(symbol)
        tick = mt5.symbol_info_tick(symbol)
        if info is None or tick is None:
            return MT5RuntimePreflight(False, True, symbol, None, None, None, None, f"cotação/metadados indisponíveis: {symbol}")

        return MT5RuntimePreflight(
            True,
            True,
            symbol,
            float(tick.bid),
            float(tick.ask),
            float(info.volume_min),
            float(info.volume_step),
            "MT5 DEMO + símbolo + cotação + limites de volume validados",
        )
    except Exception as exc:
        return MT5RuntimePreflight(False, False, symbol, None, None, None, None, f"falha no preflight: {exc}")
    finally:
        try:
            mt5.shutdown()
        except Exception:
            pass


if __name__ == "__main__":
    try:
        import MetaTrader5 as mt5
    except Exception as exc:
        print(f"MetaTrader5 indisponível: {exc}")
    else:
        result = run_preflight(mt5)
        print(result.message)
        print(f"available={result.available} demo={result.demo}")
        print(f"symbol={result.symbol} bid={result.bid} ask={result.ask}")
        print(f"volume_min={result.volume_min} volume_step={result.volume_step}")
