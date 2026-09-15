from core.ecosystem_recovery_guide import EcosystemRecoveryGuide, RecoveryActionKind
from core.global_operational_barrier import (
    BarrierDecision,
    BarrierStatus,
    RemediationResult,
)


def test_ready_recovery_guide_never_grants_execution_authority():
    guide = EcosystemRecoveryGuide().build(
        BarrierDecision(BarrierStatus.READY, "ok", (), ())
    )

    assert guide.status is BarrierStatus.READY
    assert guide.execution_authorized is False
    assert guide.items


def test_safe_repair_is_explained_but_requires_re_evaluation():
    decision = BarrierDecision(
        BarrierStatus.BLOCKED,
        "incident ativo",
        ("technical-incident",),
        (),
    )
    remediation = RemediationResult(
        attempted=True,
        repaired_components=("temporary-cache",),
        failed_components=(),
    )

    guide = EcosystemRecoveryGuide().build(decision, remediation)

    assert guide.execution_authorized is False
    assert any(item.action is RecoveryActionKind.AUTO_SAFE for item in guide.items)
    assert any("reavaliada" in item.next_step.lower() for item in guide.items)


def test_blocked_state_teaches_user_not_to_bypass_safety():
    decision = BarrierDecision(
        BarrierStatus.UNKNOWN,
        "fonte de segurança indisponível",
        ("operational-safety-store",),
        (),
    )

    guide = EcosystemRecoveryGuide().build(decision)

    assert guide.execution_authorized is False
    assert any(item.action is RecoveryActionKind.BLOCKED for item in guide.items)
    assert any("não liberar" in item.next_step.lower() for item in guide.items)
