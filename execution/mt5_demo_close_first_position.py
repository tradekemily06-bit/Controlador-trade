from __future__ import annotations

"""Read-only MT5 DEMO position inspection.

Order placement and closure must remain behind the execution lifecycle and its
single execution boundary. This helper intentionally performs no order_send.
"""

import MetaTrader5 as mt5

MAGIC = 2609001
SYMBOL = "EURUSD"


def main() -> None:
    if not mt5.initialize():
        print("MT5 indisponível; inspeção não executada.")
        return

    try:
        account = mt5.account_info()
        if account is None or account.trade_mode != mt5.ACCOUNT_TRADE_MODE_DEMO:
            print("BLOQUEADO: conta não confirmada como DEMO.")
            return
        positions = mt5.positions_get(symbol=SYMBOL) or ()
        candidates = [p for p in positions if getattr(p, "magic", None) == MAGIC]
        print(f"CONTROLADOR_DEMO_POSITIONS={len(candidates)}; INSPECAO_ONLY=True; ORDER_SEND=False")
        for position in candidates:
            print(
                f"POSITION_TICKET={getattr(position, 'ticket', None)}; "
                f"SYMBOL={getattr(position, 'symbol', None)}; "
                f"VOLUME={getattr(position, 'volume', None)}"
            )
    finally:
        mt5.shutdown()


if __name__ == "__main__":
    main()
