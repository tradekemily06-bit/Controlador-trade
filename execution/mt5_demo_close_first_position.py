from __future__ import annotations

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
        check = mt5.order_check(request)
        print(f"CLOSE_ORDER_CHECK={check}")
        if check is None or getattr(check, "retcode", 0) != 0:
            print("FECHAMENTO BLOQUEADO: order_check não aprovado.")
            return
        print("FECHAMENTO NÃO EXECUTADO: este utilitário é somente leitura e não chama order_send().")
        print("USE_THE_EXECUTION_GATEWAY=True; DEMO_ONLY=True; REAL=False")
    finally:
        mt5.shutdown()


if __name__ == "__main__":
    main()
