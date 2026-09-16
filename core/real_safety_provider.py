from __future__ import annotations

from typing import Protocol, runtime_checkable

from .p114_real_safety_gate import RealSafetyReport


@runtime_checkable
class RealSafetyProvider(Protocol):
    """Authoritative runtime source for the complete REAL safety composition."""

    def current_real_safety(self) -> RealSafetyReport:
        ...


def read_authoritative_real_safety(provider: RealSafetyProvider) -> RealSafetyReport:
    """Read and validate the runtime safety state without a fail-open fallback."""
    if not isinstance(provider, RealSafetyProvider):
        raise TypeError("real_safety_provider não implementa o contrato autoritativo.")
    report = provider.current_real_safety()
    if not isinstance(report, RealSafetyReport):
        raise TypeError("provedor de segurança REAL retornou um relatório inválido.")
    return report
