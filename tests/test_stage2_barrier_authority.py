from __future__ import annotations

from pathlib import Path

import pytest

from core.decision_freshness import DecisionFreshnessPolicy
from core.operational_runtime import build_operational_runtime


def test_runtime_global_barrier_cannot_be_replaced_or_removed(tmp_path: Path) -> None:
    runtime = build_operational_runtime(tmp_path)
    gateway = runtime.gateway

    with pytest.raises(RuntimeError, match="barreira operacional já está vinculada"):
        gateway.set_operational_barrier_provider(None)

    with pytest.raises(RuntimeError, match="barreira operacional já está vinculada"):
        gateway.set_operational_barrier_provider(lambda: None)  # type: ignore[arg-type]

    assert gateway._operational_barrier_provider is not None
    assert gateway._operational_barrier_provider_locked is True


def test_runtime_freshness_policy_cannot_be_disabled_or_replaced(tmp_path: Path) -> None:
    runtime = build_operational_runtime(tmp_path)
    gateway = runtime.gateway

    with pytest.raises(RuntimeError, match="política de frescor da decisão já está vinculada"):
        gateway.set_decision_freshness_policy(None)

    with pytest.raises(RuntimeError, match="política de frescor da decisão já está vinculada"):
        gateway.set_decision_freshness_policy(DecisionFreshnessPolicy(max_age_seconds=9999.0))

    assert gateway._decision_freshness_policy is not None
    assert gateway._decision_freshness_policy_locked is True
