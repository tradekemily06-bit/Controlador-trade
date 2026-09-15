from __future__ import annotations

import pytest

from core.global_operational_barrier import (
    BarrierStatus,
    GlobalOperationalBarrier,
    RemediationMode,
    SafetyComponent,
)


def test_all_healthy_components_allow_operation() -> None:
    decision = GlobalOperationalBarrier(
        [SafetyComponent("market-data", True), SafetyComponent("incident", True)]
    ).evaluate()

    assert decision.status is BarrierStatus.READY
    assert decision.operationally_allowed


def test_any_unhealthy_component_blocks_operation() -> None:
    decision = GlobalOperationalBarrier(
        [
            SafetyComponent("market-data", True),
            SafetyComponent("incident", False, "incidente técnico ativo"),
        ]
    ).evaluate()

    assert decision.status is BarrierStatus.BLOCKED
    assert not decision.operationally_allowed
    assert decision.blocking_components == ("incident",)


def test_safety_source_failure_is_unknown_and_blocks() -> None:
    class ExplodingComponent:
        name = "incident"
        detail = ""
        remediation_mode = RemediationMode.MANUAL_REQUIRED
        repair = None

        @property
        def healthy(self):
            raise RuntimeError("store indisponível")

    decision = GlobalOperationalBarrier([ExplodingComponent()]).evaluate()

    assert decision.status is BarrierStatus.UNKNOWN
    assert not decision.operationally_allowed
    assert "safety-state" in decision.blocking_components


def test_safe_repair_is_allowed_but_never_grants_authorization() -> None:
    repaired = []

    barrier = GlobalOperationalBarrier(
        [
            SafetyComponent(
                "temporary-state",
                False,
                "estado temporário recuperável",
                RemediationMode.AUTO_SAFE,
                lambda: repaired.append("temporary-state"),
            )
        ]
    )

    results = barrier.remediate()

    assert repaired == ["temporary-state"]
    assert results[0].attempted is True
    assert results[0].succeeded is True
    assert not barrier.evaluate().operationally_allowed


def test_manual_and_never_auto_components_are_not_touched() -> None:
    touched = []
    barrier = GlobalOperationalBarrier(
        [
            SafetyComponent("manual", False, "requires operator", RemediationMode.MANUAL_REQUIRED, lambda: touched.append("manual")),
            SafetyComponent("never", False, "security condition", RemediationMode.NEVER_AUTO, lambda: touched.append("never")),
        ]
    )

    results = barrier.remediate()

    assert touched == []
    assert {result.component for result in results} == {"manual", "never"}
    assert all(not result.attempted for result in results)


def test_blocked_barrier_raises() -> None:
    barrier = GlobalOperationalBarrier([SafetyComponent("incident", False, "ativo")])

    with pytest.raises(RuntimeError, match="ecossistema bloqueado"):
        barrier.evaluate_or_raise()
