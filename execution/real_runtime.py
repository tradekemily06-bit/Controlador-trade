from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from core.kill_switch import KillSwitch
from core.operational_safety_store import OperationalSafetyStore
from core.p112_real_execution_contract import RealExecutionAuthorization
from execution.adapter_gateway import BrokerAdapterGateway
from execution.broker_registry import BrokerRegistry
from execution.execution_ledger import ExecutionLedger
from execution.real_gateway import RealExecutionGateway


@dataclass(frozen=True)
class RealExecutionRuntime:
    """REAL composition with one authoritative, persisted safety gate."""

    authorization: RealExecutionAuthorization
    kill_switch: KillSwitch
    safety_store: OperationalSafetyStore
    ledger: ExecutionLedger
    gateway: RealExecutionGateway


def build_real_execution_runtime(
    root: str | Path,
    registry: BrokerRegistry,
    authorization: RealExecutionAuthorization,
) -> RealExecutionRuntime:
    """Build the REAL boundary only from persisted safety state.

    A missing safety file is fail-closed: REAL must never start from a fresh
    in-memory KillSwitch whose clear state could accidentally permit dispatch.
    The loaded KillSwitch is the same object injected into RealExecutionGateway.
    """
    if not isinstance(registry, BrokerRegistry):
        raise ValueError("registry inválido.")
    if not isinstance(authorization, RealExecutionAuthorization) or not authorization.active:
        raise ValueError("autorização REAL ativa é obrigatória.")

    root = Path(root)
    safety_store = OperationalSafetyStore(root / "safety.json")
    if not safety_store.path.is_file():
        raise RuntimeError("estado de segurança REAL ausente; inicialização bloqueada.")

    _, kill_switch = safety_store.load()
    ledger = ExecutionLedger(root / "execution-ledger.json")
    adapter_gateway = BrokerAdapterGateway(registry)
    gateway = RealExecutionGateway(adapter_gateway, ledger, kill_switch)
    return RealExecutionRuntime(
        authorization=authorization,
        kill_switch=kill_switch,
        safety_store=safety_store,
        ledger=ledger,
        gateway=gateway,
    )
