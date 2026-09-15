"""Global fail-closed barrier for analysis, risk, recommendation and execution.

The barrier is deliberately narrower than a broker gateway: it answers one
question only -- whether the ecosystem may produce an operationally usable
result.  A failure to read any safety source is itself a block.

Automatic recovery is limited to deterministic, local and reversible actions.
It may repair infrastructure state, but it can never clear a safety block or
re-authorize trading by itself.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable, Iterable


class BarrierStatus(str, Enum):
    READY = "READY"
    BLOCKED = "BLOCKED"
    UNKNOWN = "UNKNOWN"


class RemediationMode(str, Enum):
    AUTO_SAFE = "AUTO_SAFE"
    MANUAL_REQUIRED = "MANUAL_REQUIRED"
    NEVER_AUTO = "NEVER_AUTO"


@dataclass(frozen=True)
class BarrierDecision:
    status: BarrierStatus
    reason: str
    blocking_components: tuple[str, ...] = ()
    repaired_components: tuple[str, ...] = ()

    @property
    def operationally_allowed(self) -> bool:
        return self.status is BarrierStatus.READY


@dataclass(frozen=True)
class RemediationResult:
    component: str
    mode: RemediationMode
    attempted: bool
    succeeded: bool
    detail: str


@dataclass(frozen=True)
class SafetyComponent:
    name: str
    healthy: bool
    detail: str = ""
    remediation_mode: RemediationMode = RemediationMode.MANUAL_REQUIRED
    repair: Callable[[], None] | None = None


class GlobalOperationalBarrier:
    """Single fail-closed policy for all operationally meaningful layers.

    This class intentionally has no broker dependency.  It can therefore be
    reused by analysis, risk, leverage, recommendation and execution paths.
    """

    def __init__(self, components: Iterable[SafetyComponent] = ()) -> None:
        self._components = tuple(components)

    def evaluate(self) -> BarrierDecision:
        blocking: list[str] = []
        reasons: list[str] = []
        try:
            components = self._components
            for component in components:
                if not component.healthy:
                    blocking.append(component.name)
                    reasons.append(component.detail or f"{component.name} indisponível")
        except Exception as exc:  # fail closed if the safety source itself fails
            return BarrierDecision(
                BarrierStatus.UNKNOWN,
                f"estado de segurança indisponível: {type(exc).__name__}",
                ("safety-state",),
            )
        if blocking:
            return BarrierDecision(BarrierStatus.BLOCKED, "; ".join(reasons), tuple(blocking))
        return BarrierDecision(BarrierStatus.READY, "todas as barreiras operacionais estão saudáveis")

    def evaluate_or_raise(self) -> BarrierDecision:
        decision = self.evaluate()
        if not decision.operationally_allowed:
            raise RuntimeError(f"ecossistema bloqueado: {decision.reason}")
        return decision

    def remediate(self) -> tuple[RemediationResult, ...]:
        """Run only explicitly safe, deterministic repairs.

        A successful repair is not authorization.  The caller must evaluate
        the complete barrier again after remediation and remains blocked if
        any safety condition is still unknown or unhealthy.
        """
        results: list[RemediationResult] = []
        for component in self._components:
            if component.healthy:
                continue
            if component.remediation_mode is not RemediationMode.AUTO_SAFE:
                results.append(RemediationResult(component.name, component.remediation_mode, False, False, component.detail))
                continue
            if component.repair is None:
                results.append(RemediationResult(component.name, RemediationMode.AUTO_SAFE, False, False, "reparo seguro não configurado"))
                continue
            try:
                component.repair()
            except Exception as exc:
                results.append(RemediationResult(component.name, RemediationMode.AUTO_SAFE, True, False, f"reparo falhou: {type(exc).__name__}"))
            else:
                results.append(RemediationResult(component.name, RemediationMode.AUTO_SAFE, True, True, "reparo seguro concluído; revalidação obrigatória"))
        return tuple(results)
