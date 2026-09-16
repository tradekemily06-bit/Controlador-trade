from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .p114_real_safety_gate import RealSafetyGate, RealSafetyReport


BoolSource = Callable[[], bool]


@dataclass(frozen=True)
class RuntimeRealSafetyProvider:
    """Compose the complete REAL safety state from live authoritative sources.

    Every source is invoked on every read. There is deliberately no cached
    report and no default-safe value. The caller must supply trusted sources
    for authorization, kill switch, market health, recovery, risk approval,
    and broker availability.
    """

    authorization_active: BoolSource
    kill_switch_clear: BoolSource
    market_healthy: BoolSource
    recovery_safe: BoolSource
    risk_approved: BoolSource
    broker_available: BoolSource

    def __post_init__(self) -> None:
        sources = (
            self.authorization_active,
            self.kill_switch_clear,
            self.market_healthy,
            self.recovery_safe,
            self.risk_approved,
            self.broker_available,
        )
        if any(not callable(source) for source in sources):
            raise ValueError("todas as fontes de segurança REAL devem ser chamáveis.")

    @staticmethod
    def _read(source: BoolSource, name: str) -> bool:
        value = source()
        if not isinstance(value, bool):
            raise TypeError(f"fonte de segurança REAL inválida: {name}.")
        return value

    def current_real_safety(self) -> RealSafetyReport:
        return RealSafetyGate().evaluate(
            authorization_active=self._read(self.authorization_active, "authorization"),
            kill_switch_clear=self._read(self.kill_switch_clear, "kill_switch"),
            market_healthy=self._read(self.market_healthy, "market"),
            recovery_safe=self._read(self.recovery_safe, "recovery"),
            risk_approved=self._read(self.risk_approved, "risk"),
            broker_available=self._read(self.broker_available, "broker"),
        )
