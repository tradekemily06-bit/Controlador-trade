from __future__ import annotations

from pathlib import Path

from execution.adapter_gateway import BrokerAdapterGateway
from execution.broker_registry import BrokerRegistry
from execution.execution_ledger import ExecutionLedger
from execution.execution_lifecycle import ExecutionLifecycleStore
from execution.real_gateway import RealExecutionGateway


def build_real_execution_gateway(
    *,
    root: str | Path,
    registry: BrokerRegistry,
) -> RealExecutionGateway:
    """The sanctioned REAL gateway composition point.

    No broker adapter is executed here. Construction only wires the already
    registered broker boundary to the single durable ledger/lifecycle stores.
    """
    if not isinstance(registry, BrokerRegistry):
        raise ValueError("registry inválido.")

    root = Path(root)
    ledger = ExecutionLedger(root / "execution-ledger.json")
    lifecycle = ExecutionLifecycleStore(root / "execution-lifecycle.json")
    return RealExecutionGateway(
        BrokerAdapterGateway(registry),
        ledger,
        lifecycle,
    )
