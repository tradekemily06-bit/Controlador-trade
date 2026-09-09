from __future__ import annotations

from dataclasses import dataclass

from core.runtime_config import RuntimeConfig
from execution.p124_broker_session import BrokerSessionBoundary, BrokerSessionObservation
from execution.p125_sandbox_validation import SandboxValidationResult


@dataclass(frozen=True)
class PreRealSecurityChecklist:
    config_safe: bool
    session_safe: bool
    sandbox_safe: bool
    passed: bool


class PreRealSecurityValidator:
    """Independent fail-closed checklist; never enables REAL."""

    @staticmethod
    def validate(
        config: RuntimeConfig,
        session: BrokerSessionObservation,
        sandbox_result: SandboxValidationResult,
    ) -> PreRealSecurityChecklist:
        if not isinstance(config, RuntimeConfig):
            raise ValueError("config inválida")
        if not isinstance(sandbox_result, SandboxValidationResult):
            raise ValueError("resultado sandbox inválido")

        config_safe = config.mode.value == "DEMO" and config.real_enabled is False
        session_safe = not BrokerSessionBoundary.is_usable(session)
        sandbox_safe = sandbox_result.external_id is None or sandbox_result.duplicate_blocked
        passed = config_safe and session_safe and sandbox_safe
        return PreRealSecurityChecklist(config_safe, session_safe, sandbox_safe, passed)
