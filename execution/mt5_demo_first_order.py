from __future__ import annotations

from execution.icmarkets_mt5_demo_adapter import ICMarketsMT5DemoAdapter
from execution.ports import ExecutionMode, ExecutionRequest
from core.models import Signal


def main() -> None:
    request = ExecutionRequest(
        symbol="EURUSD",
        signal=Signal.COMPRA,
        amount=0.01,
        duration_seconds=60,
        mode=ExecutionMode.DEMO,
        request_id="mt5-demo-first-order",
    )

    adapter = ICMarketsMT5DemoAdapter()
    result = adapter.execute(request)
    print(result)
    print("DEMO_ONLY=True; REAL=False")


if __name__ == "__main__":
    main()
