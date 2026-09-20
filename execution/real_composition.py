from __future__ import annotations

from pathlib import Path

from execution.adapter_gateway import BrokerAdapterGateway
from execution.broker_registry import BrokerRegistry
from execution.execution_ledger import ExecutionLedger
from execution.execution_lifecycle import ExecutionLifecycleStore
from core.kill_switch import KillSwitch
from execution.real_gateway import RealExecutionGateway


def build_real_execution_gateway(
    *,
    root: str | Path,
    registry: BrokerRegistry,
    kill_switch: KillSwitch | None = None,
) -> RealExecutionGateway:
    """The sanctioned REAL gateway composition point.

    No broker adapter is executed here. Construction only wires the already
    registered broker boundary to the single durable ledger/lifecycle stores.
    """
    if type(registry) is not BrokerRegistry:
        raise ValueError("registry inválido.")
    if kill_switch is not None and type(kill_switch) is not KillSwitch:
        raise ValueError("kill_switch inválido.")
    root = Path(root)
    # REAL must use a durable/shared kill switch so a stop issued by one
    # process is observed by every other REAL process before dispatch.
    if kill_switch is None:
        kill_switch = KillSwitch(root / "real-kill-switch.json")
    elif getattr(kill_switch, "_path", None) is None:
        raise ValueError("REAL exige kill switch persistente e compartilhado.")
    ledger = ExecutionLedger(root / "execution-ledger.json")
    lifecycle = ExecutionLifecycleStore(root / "execution-lifecycle.json")
    return RealExecutionGateway(
        BrokerAdapterGateway(registry),
        ledger,
        lifecycle,
        kill_switch,
    )
