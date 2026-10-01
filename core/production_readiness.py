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
    """Deployment readiness signal; it never authorizes or dispatches REAL."""

    def __init__(self, *, kill_switch: KillSwitch, execution_ledger: ExecutionLedger) -> None:
        if not isinstance(kill_switch, KillSwitch):
            raise ValueError("kill_switch inválido.")
        if not isinstance(execution_ledger, ExecutionLedger):
            raise ValueError("execution_ledger inválido.")
        self.kill_switch = kill_switch
        self.execution_ledger = execution_ledger

    def evaluate(self, *, mode: ExecutionMode = ExecutionMode.DEMO, real_enabled: bool = False) -> ReadinessReport:
        if not isinstance(mode, ExecutionMode):
            raise ValueError("modo de execução inválido.")
        if not isinstance(real_enabled, bool):
            raise ValueError("real_enabled deve ser booleano.")
        if not self.kill_switch.allows_execution():
            return ReadinessReport(ReadinessState.NOT_READY, ("kill switch ativo",))
        if mode is ExecutionMode.REAL:
            if not real_enabled:
                return ReadinessReport(
                    ReadinessState.NOT_READY,
                    ("REAL exige habilitação explícita de configuração; nenhuma autorização foi concedida.",),
                )
            return ReadinessReport(
                ReadinessState.READY_REAL,
                ("configuração REAL explicitamente habilitada; autorização/admissão/confirmacão ainda são obrigatórias.",),
            )
        return ReadinessReport(
            ReadinessState.READY_DEMO,
            ("execução DEMO pronta.",),
        )
