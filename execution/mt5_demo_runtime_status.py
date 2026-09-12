from __future__ import annotations

from typing import Any

from execution.mt5_demo_health import MT5DemoHealth, check_mt5_demo_health


def mt5_demo_runtime_status(mt5: Any = None) -> dict[str, object]:
    """Return truthful MT5 DEMO runtime state without placing an order.

    A configured/validated DEMO boundary is not the same thing as a currently
    reachable MT5 terminal. When no runtime module is supplied, the result is
    explicitly reported as NOT_CHECKED rather than inferred as connected.
    """
    if mt5 is None:
        try:
            import MetaTrader5 as mt5_module  # type: ignore
        except ImportError:
            return {
                "state": "NOT_AVAILABLE",
                "available": False,
                "demo_account": False,
                "message": "MetaTrader5 não instalado neste runtime.",
            }
        mt5 = mt5_module

    health: MT5DemoHealth = check_mt5_demo_health(mt5)
    return {
        "state": "ONLINE_DEMO" if health.available else "OFFLINE",
        "available": health.available,
        "demo_account": health.demo_account,
        "message": health.message,
    }
