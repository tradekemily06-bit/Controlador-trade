from __future__ import annotations

from pathlib import Path

from core.operational_runtime import build_operational_runtime
from execution.paper import PaperExecutor


def test_runtime_accepts_injected_demo_executor(tmp_path: Path):
    executor = PaperExecutor()
    runtime = build_operational_runtime(tmp_path, executor=executor)
    assert runtime.gateway._executor._port is executor
