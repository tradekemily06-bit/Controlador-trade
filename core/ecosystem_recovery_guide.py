"""Human-readable recovery guidance for the ecosystem's Mode of Use.

This layer explains what the ecosystem did (or could not do) after an operational
problem. It is educational/auditable only: it never grants execution authority,
never resolves incidents, and never disables safety controls.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from core.global_operational_barrier import (
    BarrierDecision,
    BarrierStatus,
    RemediationResult,
)


class RecoveryActionKind(str, Enum):
    AUTO_SAFE = "AUTO_SAFE"
    USER_ACTION = "USER_ACTION"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class RecoveryGuideItem:
    title: str
    explanation: str
    action: RecoveryActionKind
    next_step: str


@dataclass(frozen=True)
class RecoveryGuide:
    status: BarrierStatus
    title: str
    summary: str
    items: tuple[RecoveryGuideItem, ...]
    execution_authorized: bool = False


class EcosystemRecoveryGuide:
    """Converts barrier/remediation facts into concise user-facing guidance."""

    def build(
        self,
        decision: BarrierDecision,
        remediation: tuple[RemediationResult, ...] = (),
    ) -> RecoveryGuide:
        if not isinstance(decision, BarrierDecision):
            raise ValueError("decisão da barreira é obrigatória.")
        if not isinstance(remediation, tuple) or not all(isinstance(item, RemediationResult) for item in remediation):
            raise ValueError("resultado de remediação inválido.")

        if decision.status is BarrierStatus.READY:
            return RecoveryGuide(
                status=BarrierStatus.READY,
                title="Sistema operacional",
                summary="As verificações de segurança estão íntegras. Nenhuma ação de recuperação é necessária.",
                items=(
                    RecoveryGuideItem(
                        "Verificação concluída",
                        "A barreira global foi reavaliada e todos os componentes necessários estão saudáveis.",
                        RecoveryActionKind.BLOCKED,
                        "Nenhuma intervenção necessária.",
                    ),
                ),
                execution_authorized=False,
            )

        items: list[RecoveryGuideItem] = []
        repaired = tuple(item.component for item in remediation if item.attempted and item.succeeded)
        if repaired:
            items.append(
                RecoveryGuideItem(
                    "Correção segura realizada",
                    f"O ecossistema conseguiu corrigir automaticamente, de forma reversível e sem alterar autoridade financeira: {', '.join(repaired)}.",
                    RecoveryActionKind.AUTO_SAFE,
                    "A barreira precisa ser reavaliada antes de qualquer retomada.",
                )
            )

        if decision.blocking_components:
            blocked = ", ".join(decision.blocking_components)
            items.append(
                RecoveryGuideItem(
                    "Operação permanece bloqueada",
                    f"A proteção detectou componentes que ainda não estão seguros: {blocked}.",
                    RecoveryActionKind.BLOCKED,
                    "Não liberar COMPRA/VENDA nem execução enquanto a barreira não estiver READY.",
                )
            )

        items.append(
            RecoveryGuideItem(
                "Se for necessária intervenção",
                "O modo de usar deve mostrar exatamente o componente, o motivo do bloqueio e o procedimento seguro para corrigi-lo, sem pedir ao usuário para contornar a proteção.",
                RecoveryActionKind.USER_ACTION,
                "Depois da correção, reavalie novamente todas as proteções; a retomada não é automática por causa de uma correção isolada.",
            )
        )

        return RecoveryGuide(
            status=decision.status,
            title="Recuperação e retomada segura",
            summary="O ecossistema entrou em modo protegido. Ele pode tentar apenas correções explicitamente classificadas como seguras; o restante exige intervenção e nova validação.",
            items=tuple(items),
            execution_authorized=False,
        )
