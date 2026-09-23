from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class AutomationClass(str, Enum):
    SAFE = "SAFE"
    REQUIRES_USER = "REQUIRES_USER"
    FORBIDDEN = "FORBIDDEN"


class SafeAutomationAction(str, Enum):
    JOURNAL_OPERATION = "JOURNAL_OPERATION"
    UPDATE_STATISTICS = "UPDATE_STATISTICS"
    RECORD_AUDIT = "RECORD_AUDIT"
    REFRESH_DERIVED_STATE = "REFRESH_DERIVED_STATE"
    RELOAD_PERSISTED_STATE = "RELOAD_PERSISTED_STATE"
    RECONNECT_READ_ONLY_DATA = "RECONNECT_READ_ONLY_DATA"


class UserAction(str, Enum):
    EXECUTE_OPERATION = "EXECUTE_OPERATION"
    AUTHORIZE_REAL = "AUTHORIZE_REAL"
    CHANGE_RISK_LIMITS = "CHANGE_RISK_LIMITS"
    RESOLVE_UNKNOWN_EXECUTION = "RESOLVE_UNKNOWN_EXECUTION"
    DISABLE_KILL_SWITCH = "DISABLE_KILL_SWITCH"
    CHANGE_SECURITY_CONFIGURATION = "CHANGE_SECURITY_CONFIGURATION"
    CHANGE_BROKER_CREDENTIALS = "CHANGE_BROKER_CREDENTIALS"


class SafeAutomationPolicy:
    """Classifies autonomy without granting trading or security authority.

    Safe automation is allowed only for bookkeeping, derived state and
    read-only recovery/maintenance. Anything that can authorize money movement,
    weaken a safety boundary, or resolve an uncertain execution stays manual.
    """

    _SAFE = frozenset(item.value for item in SafeAutomationAction)
    _USER = frozenset(item.value for item in UserAction)

    @classmethod
    def classify(cls, action: str) -> AutomationClass:
        normalized = str(action).strip().upper()
        if normalized in cls._SAFE:
            return AutomationClass.SAFE
        if normalized in cls._USER:
            return AutomationClass.REQUIRES_USER
        return AutomationClass.FORBIDDEN

    @classmethod
    def is_safe(cls, action: str) -> bool:
        return cls.classify(action) is AutomationClass.SAFE


@dataclass(frozen=True)
class MaintenanceDecision:
    action: str
    classification: AutomationClass
    allowed_automatically: bool
    reason: str


def classify_maintenance(action: str) -> MaintenanceDecision:
    classification = SafeAutomationPolicy.classify(action)
    if classification is AutomationClass.SAFE:
        return MaintenanceDecision(
            action=str(action),
            classification=classification,
            allowed_automatically=True,
            reason="manutenção derivada/read-only sem autoridade operacional",
        )
    if classification is AutomationClass.REQUIRES_USER:
        return MaintenanceDecision(
            action=str(action),
            classification=classification,
            allowed_automatically=False,
            reason="ação altera autoridade, segurança ou estado financeiro",
        )
    return MaintenanceDecision(
        action=str(action),
        classification=classification,
        allowed_automatically=False,
        reason="ação fora da lista explícita de automações permitidas",
    )
