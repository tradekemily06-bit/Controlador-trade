from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class RepairDecision(str, Enum):
    ALLOW_BOUNDED_REPAIR = "ALLOW_BOUNDED_REPAIR"
    ALERT_AND_BLOCK = "ALERT_AND_BLOCK"


@dataclass(frozen=True)
class RepairRequest:
    """Facts about a proposed repair; this policy never performs the repair."""

    action: str
    local_only: bool
    reversible: bool
    deterministic: bool
    prevalidated: bool
    external_side_effects: bool
    touches_execution_state: bool
    requires_human_supervision: bool
    cooldown_elapsed: bool
    maintenance_lock_clear: bool
    attempts_used: int
    max_attempts: int


@dataclass(frozen=True)
class RepairAuthorization:
    decision: RepairDecision
    allowed: bool
    reason: str


class SelfRepairPolicy:
    """Fail-closed authorization boundary for explicitly allowlisted repairs.

    This class only decides whether a proposed repair meets the safety contract.
    It does not execute repairs, restart processes, contact providers, alter
    execution permissions, or bypass recovery/reconciliation gates.

    A repair name is not evidence of safety. New repair actions must be reviewed
    and explicitly allowlisted before this policy can authorize them.
    """

    # Keep the initial allowlist intentionally narrow. Adding an action requires
    # a separately reviewed implementation and tests proving its bounded scope.
    # Process/terminal recovery remains blocked until the supervisor can
    # prove execution is quiescent and reconcile broker state. A caller-provided
    # boolean is not sufficient evidence that restarting MT5 is safe.
    ALLOWED_ACTIONS = frozenset({
        "clear_stale_local_cache",
    })

    @staticmethod
    def evaluate(request: RepairRequest) -> RepairAuthorization:
        if not isinstance(request, RepairRequest):
            return RepairAuthorization(
                RepairDecision.ALERT_AND_BLOCK,
                False,
                "pedido de reparo inválido; supervisão humana necessária",
            )

        if not isinstance(request.action, str) or not request.action.strip():
            return SelfRepairPolicy._blocked("ação de reparo ausente ou inválida")
        if request.action not in SelfRepairPolicy.ALLOWED_ACTIONS:
            return SelfRepairPolicy._blocked(
                "ação de reparo não consta na lista explicitamente autorizada"
            )
        if any(
            not isinstance(value, bool)
            for value in (
                request.local_only,
                request.reversible,
                request.deterministic,
                request.prevalidated,
                request.external_side_effects,
                request.touches_execution_state,
                request.requires_human_supervision,
                request.cooldown_elapsed,
                request.maintenance_lock_clear,
            )
        ):
            return SelfRepairPolicy._blocked("atributos de segurança inválidos")
        if (
            isinstance(request.attempts_used, bool)
            or not isinstance(request.attempts_used, int)
            or isinstance(request.max_attempts, bool)
            or not isinstance(request.max_attempts, int)
            or request.attempts_used < 0
            or request.max_attempts < 1
            or request.attempts_used >= request.max_attempts
        ):
            return SelfRepairPolicy._blocked(
                "limite de tentativas atingido ou configuração de tentativas inválida"
            )

        blockers = []
        if not request.local_only:
            blockers.append("reparo não é estritamente local")
        if not request.reversible:
            blockers.append("reparo não é reversível")
        if not request.deterministic:
            blockers.append("resultado do reparo não é determinístico")
        if not request.prevalidated:
            blockers.append("reparo não foi validado previamente")
        if request.external_side_effects:
            blockers.append("reparo pode produzir efeitos externos")
        if request.touches_execution_state:
            blockers.append("reparo afeta estado de execução ou operações")
        if request.requires_human_supervision:
            blockers.append("reparo exige supervisão humana")
        if not request.cooldown_elapsed:
            blockers.append("período de espera controlada ainda não terminou")
        if not request.maintenance_lock_clear:
            blockers.append("bloqueio de manutenção está ativo")

        if blockers:
            return SelfRepairPolicy._blocked("; ".join(blockers))

        return RepairAuthorization(
            RepairDecision.ALLOW_BOUNDED_REPAIR,
            True,
            "reparo explicitamente autorizado, local, reversível, determinístico, previamente validado e dentro do limite",
        )

    @staticmethod
    def _blocked(reason: str) -> RepairAuthorization:
        return RepairAuthorization(RepairDecision.ALERT_AND_BLOCK, False, reason)
