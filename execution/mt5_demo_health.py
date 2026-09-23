from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from execution.mt5_session import coordinator_for


@dataclass(frozen=True)
class MT5DemoHealth:
    available: bool
    demo_account: bool
    message: str


def check_mt5_demo_health(mt5: Any) -> MT5DemoHealth:
    """Perform a read-only preflight; never sends or modifies an order."""
    owner=f"health:{id(mt5)}"
    coordinator=coordinator_for(mt5)
    acquired=False
    try:
        acquired=coordinator.acquire(mt5, mode="DEMO", owner=owner)
        if not acquired:
            return MT5DemoHealth(False, False, f"MT5 indisponível: {mt5.last_error()}")
        with coordinator.operation(mt5, mode="DEMO", owner=owner):
            account = mt5.account_info()
        demo_mode = getattr(mt5, "ACCOUNT_TRADE_MODE_DEMO", None)
        is_demo = (
            account is not None
            and demo_mode is not None
            and getattr(account, "trade_mode", None) == demo_mode
        )
        if not is_demo:
            return MT5DemoHealth(False, False, "conta MT5 não confirmada como DEMO")
        return MT5DemoHealth(True, True, "MT5 DEMO disponível")
    except Exception as exc:
        return MT5DemoHealth(False, False, f"falha no preflight MT5: {exc}")
    finally:
        if acquired:
            coordinator.release(mt5, owner=owner)


if __name__ == "__main__":
    try:
        import MetaTrader5 as mt5
    except Exception as exc:
        print(f"MetaTrader5 indisponível: {exc}")
    else:
        result = check_mt5_demo_health(mt5)
        print(result.message)
        print(f"available={result.available} demo_account={result.demo_account}")
