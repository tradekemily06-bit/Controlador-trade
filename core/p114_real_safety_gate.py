from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class RealSafetyState(str, Enum):
    READY = "READY"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class RealSafetyReport:
    state: RealSafetyState
    reasons: tuple[str, ...]

    @property
    def ready(self) -> bool:
        return self.state is RealSafetyState.READY


class RealSafetyGate:
    """Fail-closed composition of explicit REAL safety prerequisites."""

    def evaluate(self, *, authorization_active: bool, kill_switch_clear: bool,
                 market_healthy: bool, recovery_safe: bool, risk_approved: bool,
                 broker_available: bool) -> RealSafetyReport:
        for value in (authorization_active, kill_switch_clear, market_healthy, recovery_safe, risk_approved, broker_available):
            if type(value) is not bool:
                raise ValueError("pré-requisitos da barreira REAL precisam ser booleanos.")
        reasons: list[str] = []
        checks = (
            (authorization_active, "autorização REAL não está ativa"),
            (kill_switch_clear, "kill switch ativo"),
            (market_healthy, "dados de mercado não estão saudáveis"),
            (recovery_safe, "recovery não está seguro"),
            (risk_approved, "risco não aprovado"),
            (broker_available, "adaptador da corretora indisponível"),
        )
        for ok, reason in checks:
            if not ok:
                reasons.append(reason)
        return RealSafetyReport(RealSafetyState.READY if not reasons else RealSafetyState.BLOCKED, tuple(reasons))
