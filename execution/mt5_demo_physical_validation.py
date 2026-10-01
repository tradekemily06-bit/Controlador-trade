from __future__ import annotations

"""One-shot physical MT5 DEMO validation.

This script is intentionally separate from the decision engine. It performs a
small, explicit round-trip against a connected DEMO MT5 terminal:
preflight -> order_check -> order_send -> identify the newly created position
-> order_check close -> order_send close -> verify no position remains.

It never permits a REAL account and never stores credentials.
"""

from datetime import datetime, timezone
import math

import MetaTrader5 as mt5

MAGIC = 2609001
SYMBOL = "EURUSD"


def fail(message: str) -> None:
    print(f"VALIDATION=BLOCKED; {message}")


def main() -> int:
    started_at = datetime.now(timezone.utc).isoformat()

    if not mt5.initialize():
        fail(f"MT5 indisponível: {mt5.last_error()}")
        return 2

    try:
        account = mt5.account_info()
        if account is None:
            fail("account_info indisponível.")
            return 2
        if getattr(account, "trade_mode", None) != mt5.ACCOUNT_TRADE_MODE_DEMO:
            fail("conta não confirmada como DEMO; nenhuma ordem será enviada.")
            return 3

        if not mt5.symbol_select(SYMBOL, True):
            fail(f"símbolo não disponível: {SYMBOL}")
            return 4

        info = mt5.symbol_info(SYMBOL)
        tick = mt5.symbol_info_tick(SYMBOL)
        if info is None or tick is None:
            fail("metadados ou cotação indisponíveis.")
            return 5

        minimum = float(getattr(info, "volume_min", 0.0))
        step = float(getattr(info, "volume_step", 0.0))
        maximum = float(getattr(info, "volume_max", 0.0))
        if not all(math.isfinite(x) and x > 0 for x in (minimum, step, maximum)):
            fail("limites de volume inválidos.")
            return 6
        if minimum > maximum:
            fail("volume_min maior que volume_max.")
            return 6

        # Use the broker's own minimum valid lot; never silently round a user
        # supplied amount because this validation is deliberately self-contained.
        volume = minimum
        steps = (volume - minimum) / step
        if not math.isclose(steps, round(steps), rel_tol=0.0, abs_tol=1e-9):
            fail("volume mínimo não respeita o volume_step.")
            return 6

        existing = tuple(
            p for p in (mt5.positions_get(symbol=SYMBOL) or ())
            if getattr(p, "magic", None) == MAGIC
        )
        if existing:
            fail(
                f"já existem {len(existing)} posição(ões) ControladorTrading no símbolo; "
                "a validação não tocará em posição preexistente."
            )
            return 7

        ask = float(getattr(tick, "ask", 0.0))
        if not math.isfinite(ask) or ask <= 0:
            fail("ask inválido.")
            return 8

        open_request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": SYMBOL,
            "volume": volume,
            "type": mt5.ORDER_TYPE_BUY,
            "price": ask,
            "deviation": 20,
            "magic": MAGIC,
            "comment": "ControladorTrading-DEMO-PHYSICAL-OPEN",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        check = mt5.order_check(open_request)
        print(f"OPEN_ORDER_CHECK={check}")
        if check is None or getattr(check, "retcode", 0) != 0:
            fail("order_check da abertura não aprovado.")
            return 9

        result = mt5.order_send(open_request)
        print(f"OPEN_ORDER_RESULT={result}")
        if result is None or getattr(result, "retcode", None) != mt5.TRADE_RETCODE_DONE:
            fail("order_send da abertura não confirmado pelo MT5.")
            return 10

        positions = tuple(
            p for p in (mt5.positions_get(symbol=SYMBOL) or ())
            if getattr(p, "magic", None) == MAGIC
        )
        if len(positions) != 1:
            fail(
                f"após a abertura, esperado exatamente 1 posição nova; "
                f"encontradas={len(positions)}."
            )
            return 11

        position = positions[0]
        position_ticket = int(position.ticket)
        position_volume = float(position.volume)
        position_symbol = str(position.symbol)
        close_tick = mt5.symbol_info_tick(position_symbol)
        if close_tick is None:
            fail("cotação indisponível para fechamento.")
            return 12

        is_buy = getattr(position, "type", None) == mt5.POSITION_TYPE_BUY
        close_price = float(close_tick.bid if is_buy else close_tick.ask)
        close_type = mt5.ORDER_TYPE_SELL if is_buy else mt5.ORDER_TYPE_BUY
        if not math.isfinite(close_price) or close_price <= 0:
            fail("preço de fechamento inválido.")
            return 12

        close_request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": position_symbol,
            "volume": position_volume,
            "type": close_type,
            "position": position_ticket,
            "price": close_price,
            "deviation": 20,
            "magic": MAGIC,
            "comment": "ControladorTrading-DEMO-PHYSICAL-CLOSE",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        close_check = mt5.order_check(close_request)
        print(f"CLOSE_ORDER_CHECK={close_check}")
        if close_check is None or getattr(close_check, "retcode", 0) != 0:
            fail("order_check do fechamento não aprovado.")
            return 13

        close_result = mt5.order_send(close_request)
        print(f"CLOSE_ORDER_RESULT={close_result}")
        if close_result is None or getattr(close_result, "retcode", None) != mt5.TRADE_RETCODE_DONE:
            fail("order_send do fechamento não confirmado pelo MT5.")
            return 14

        remaining = tuple(
            p for p in (mt5.positions_get(symbol=SYMBOL) or ())
            if getattr(p, "magic", None) == MAGIC
        )
        finished_at = datetime.now(timezone.utc).isoformat()

        print("VALIDATION=PASSED")
        print("DEMO_ONLY=True")
        print("REAL=False")
        print(f"SYMBOL={SYMBOL}")
        print(f"VOLUME={volume}")
        print(f"POSITION_TICKET={position_ticket}")
        print(f"OPEN_ORDER={getattr(result, 'order', None)}")
        print(f"OPEN_DEAL={getattr(result, 'deal', None)}")
        print(f"CLOSE_ORDER={getattr(close_result, 'order', None)}")
        print(f"CLOSE_DEAL={getattr(close_result, 'deal', None)}")
        print(f"REMAINING_CONTROLADOR_POSITIONS={len(remaining)}")
        print(f"STARTED_AT={started_at}")
        print(f"FINISHED_AT={finished_at}")

        if remaining:
            fail("posição Controlador ainda permanece aberta após fechamento.")
            return 15

        return 0
    finally:
        mt5.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
