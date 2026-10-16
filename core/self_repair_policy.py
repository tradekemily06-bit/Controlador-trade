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
    external_side_effects: bool = False
    touches_execution_state: bool = False
    requires_human_supervision: bool = False
    attempts_used: int = 0
    max_attempts: int = 1


@dataclass(frozen=True)
class RepairAuthorization:
    decision: RepairDecision
    allowed: bool
    reason: str


class SelfRepairPolicy:
    """Fail-closed authorization boundary for bounded, low-risk self-repair.

    This class only decides whether a proposed repair meets the safety contract.
    It does not execute repairs, restart processes, contact providers, alter
    execution permissions, or bypass recovery/reconciliation gates.
    """

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

        if blockers:
            return SelfRepairPolicy._blocked("; ".join(blockers))

        return RepairAuthorization(
            RepairDecision.ALLOW_BOUNDED_REPAIR,
            True,
            "reparo local, reversível, determinístico, previamente validado e dentro do limite",
        )

    @staticmethod
    def _blocked(reason: str) -> RepairAuthorization:
        return RepairAuthorization(RepairDecision.ALERT_AND_BLOCK, False, reason)
