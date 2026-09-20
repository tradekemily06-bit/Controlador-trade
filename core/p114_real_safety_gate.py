from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class RealSafetyState(str, Enum):
    READY = "READY"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class RealSafetyReport:
    state: RealSafetyState
    authorization_id: str
    reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        if type(self.authorization_id) is not str or not self.authorization_id.strip() or self.authorization_id != self.authorization_id.strip():
            raise ValueError("authorization_id da barreira REAL inválido.")
        if not isinstance(self.state, RealSafetyState):
            raise ValueError("estado da barreira REAL inválido.")
        if not isinstance(self.reasons, tuple) or any(
            type(reason) is not str or not reason.strip() for reason in self.reasons
        ):
            raise ValueError("reasons da barreira REAL inválidos.")
        if self.state is RealSafetyState.READY and self.reasons:
            raise ValueError("barreira REAL READY não pode carregar motivos de bloqueio.")
        if self.state is RealSafetyState.BLOCKED and not self.reasons:
            raise ValueError("barreira REAL BLOCKED precisa registrar o motivo do bloqueio.")

    @property
    def ready(self) -> bool:
        return self.state is RealSafetyState.READY


class RealSafetyGate:
    """Fail-closed composition of explicit REAL safety prerequisites."""

    def evaluate(self, *, authorization_active: bool, kill_switch_clear: bool,
                 market_healthy: bool, recovery_safe: bool, risk_approved: bool,
                 broker_available: bool, authorization_id: str) -> RealSafetyReport:
        if type(authorization_id) is not str or not authorization_id.strip() or authorization_id != authorization_id.strip():
            raise ValueError("authorization_id é obrigatório e canônico.")
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
        return RealSafetyReport(RealSafetyState.READY if not reasons else RealSafetyState.BLOCKED, authorization_id.strip(), tuple(reasons))
