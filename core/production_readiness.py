from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from core.kill_switch import KillSwitch
from execution.execution_ledger import ExecutionLedger
from execution.ports import ExecutionMode


class ReadinessState(str, Enum):
    NOT_READY = "NOT_READY"
    READY_DEMO = "READY_DEMO"
    READY_REAL = "READY_REAL"


@dataclass(frozen=True)
class ReadinessReport:
    state: ReadinessState
    reasons: tuple[str, ...]

    @property
    def ready(self) -> bool:
        return self.state is not ReadinessState.NOT_READY


class ProductionReadiness:
    """Safety gate for deployment readiness; never enables REAL execution."""

    def __init__(self, *, kill_switch: KillSwitch, execution_ledger: ExecutionLedger) -> None:
        if not isinstance(kill_switch, KillSwitch):
            raise ValueError("kill_switch inválido.")
        if not isinstance(execution_ledger, ExecutionLedger):
            raise ValueError("execution_ledger inválido.")
        self.kill_switch = kill_switch
        self.execution_ledger = execution_ledger

    def evaluate(self, *, mode: ExecutionMode = ExecutionMode.DEMO) -> ReadinessReport:
        if not isinstance(mode, ExecutionMode):
            raise ValueError("modo de execução inválido.")
        if mode is ExecutionMode.REAL:
            return ReadinessReport(
                ReadinessState.NOT_READY,
                ("execução REAL permanece bloqueada nesta etapa",),
            )
        if not self.kill_switch.allows_execution():
            return ReadinessReport(
                ReadinessState.NOT_READY,
                ("kill switch ativo",),
            )
        return ReadinessReport(
            ReadinessState.READY_DEMO,
            ("somente execução DEMO está habilitada nesta etapa",),
        )
