from __future__ import annotations

"""Read-only DEMO position-close preflight.

This module intentionally never calls ``order_send``. Closing a position is an
operational action and must pass through the ecosystem execution boundary so
the global fail-closed barrier, kill switch, incident state, reconciliation,
and audit controls are evaluated immediately before broker dispatch.
"""

import MetaTrader5 as mt5

MAGIC = 2609001
SYMBOL = "EURUSD"


def main() -> None:
    if not mt5.initialize():
        print(f"MT5 indisponível: {mt5.last_error()}")
        return

    try:
        account = mt5.account_info()
        if account is None or account.trade_mode != mt5.ACCOUNT_TRADE_MODE_DEMO:
            print("BLOQUEADO: conta não confirmada como DEMO.")
            return
        positions = mt5.positions_get(symbol=SYMBOL) or ()
        candidates = [p for p in positions if getattr(p, "magic", None) == MAGIC]
        if len(candidates) != 1:
            print(f"BLOQUEADO: esperado exatamente 1 posição do Controlador; encontrado={len(candidates)}")
            return

        position = candidates[0]
        tick = mt5.symbol_info_tick(position.symbol)
        if tick is None:
            print("BLOQUEADO: cotação indisponível.")
            return

        is_buy = position.type == mt5.POSITION_TYPE_BUY
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": position.symbol,
            "volume": float(position.volume),
            "type": mt5.ORDER_TYPE_SELL if is_buy else mt5.ORDER_TYPE_BUY,
            "position": int(position.ticket),
            "price": tick.bid if is_buy else tick.ask,
            "deviation": 20,
            "magic": MAGIC,
            "comment": "ControladorTrading-DEMO-CLOSE",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        # Read-only preflight only. Do not call order_check/order_send here:
        # either operation could become a second, unguarded execution boundary.
        print("CLOSE_PREFLIGHT_READY=True")
        print("CLOSE_PREFLIGHT_DEMO_ONLY=True")
        print("CLOSE_PREFLIGHT_DISPATCH_ALLOWED=False")
        print("CLOSE_PREFLIGHT_REASON=fechamento deve passar pelo ExecutionGateway/global barrier")
        print(f"CLOSE_PREFLIGHT_POSITION={int(position.ticket)}")
        print(f"CLOSE_PREFLIGHT_SYMBOL={position.symbol}")
        print(f"CLOSE_PREFLIGHT_VOLUME={float(position.volume)}")
        print(f"CLOSE_PREFLIGHT_SIDE={'SELL' if is_buy else 'BUY'}")
        print(f"CLOSE_PREFLIGHT_PRICE={tick.bid if is_buy else tick.ask}")
        print(f"CLOSE_PREFLIGHT_REQUEST={request}")
    finally:
        mt5.shutdown()


if __name__ == "__main__":
    main()
