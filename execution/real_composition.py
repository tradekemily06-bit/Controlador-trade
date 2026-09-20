from __future__ import annotations

from pathlib import Path

from execution.adapter_gateway import BrokerAdapterGateway
from execution.broker_registry import BrokerRegistry
from execution.execution_ledger import ExecutionLedger
from execution.execution_lifecycle import ExecutionLifecycleStore
from core.kill_switch import KillSwitch
from execution.real_execution_locks import RealExecutionLocks
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
    global_lock_path = RealExecutionLocks(
        root / "execution-ledger.json"
    ).global_lock_path
    # REAL must use a durable/shared kill switch coordinated by the same
    # global REAL barrier used by dispatch/recovery.
    if kill_switch is None:
        kill_switch = KillSwitch(
            root / "real-kill-switch.json",
            coordination_lock_path=global_lock_path,
        )
    elif getattr(kill_switch, "_path", None) is None:
        raise ValueError("REAL exige kill switch persistente e compartilhado.")
    elif getattr(kill_switch, "_coordination_lock_path", None) != global_lock_path:
        raise ValueError(
            "REAL exige kill switch coordenado pela mesma barreira global de execução."
        )
    ledger = ExecutionLedger(root / "execution-ledger.json")
    lifecycle = ExecutionLifecycleStore(root / "execution-lifecycle.json")
    return RealExecutionGateway(
        BrokerAdapterGateway(registry),
        ledger,
        lifecycle,
        kill_switch,
    )
