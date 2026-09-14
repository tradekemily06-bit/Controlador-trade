from __future__ import annotations

from core.models import Signal
from execution.ports import ExecutionMode, ExecutionRequest


"""Safe DEMO request example.

This module deliberately does not dispatch directly to a broker adapter.
All execution must pass through the orchestrated decision, contextual-risk,
market-data, safety and reconciliation gates first.
"""


def build_demo_request() -> ExecutionRequest:
    """Build an example request without authorizing or submitting it."""
    return ExecutionRequest(
        symbol="EURUSD",
        signal=Signal.COMPRA,
        amount=0.01,
        duration_seconds=60,
        mode=ExecutionMode.DEMO,
        request_id="mt5-demo-first-order",
    )


def main() -> None:
    request = build_demo_request()
    print(request)
    print("DEMO_REQUEST_ONLY=True; DIRECT_BROKER_DISPATCH=False")
    print("Use the orchestrated DEMO flow after all required gates are satisfied.")


if __name__ == "__main__":
    main()
