from __future__ import annotations

import os
from pathlib import Path

import pytest

from core.operational_runtime import build_operational_runtime
from execution.paper import PaperExecutor


def test_public_multi_instance_startup_fails_closed(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("CONTROLADOR_SAAS_PUBLIC", "true")
    monkeypatch.setenv("CONTROLADOR_MULTI_INSTANCE", "true")
    with pytest.raises(RuntimeError, match="shared authoritative operational state provider"):
        build_operational_runtime(tmp_path)


def test_arbitrary_executor_cannot_enter_production_runtime(tmp_path: Path):
    class UnsafeExecutor:
        def execute(self, request):
            raise AssertionError("unsafe executor must never be accepted")

    with pytest.raises(RuntimeError, match="executor operacional não autorizado"):
        build_operational_runtime(tmp_path, executor=UnsafeExecutor())


def test_paper_executor_stays_inside_authoritative_demo_risk_guard(tmp_path: Path):
    runtime = build_operational_runtime(tmp_path, executor=PaperExecutor())
    assert runtime.demo_risk_state is not None
    assert runtime.risk_state_provider is runtime.demo_risk_state
    assert runtime.gateway is not None


def test_production_topology_does_not_enable_real_execution(tmp_path: Path):
    runtime = build_operational_runtime(tmp_path)
    assert runtime.gateway is not None
    assert not hasattr(runtime.gateway, "execute_real")
