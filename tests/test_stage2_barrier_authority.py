from __future__ import annotations

from pathlib import Path

import pytest

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
