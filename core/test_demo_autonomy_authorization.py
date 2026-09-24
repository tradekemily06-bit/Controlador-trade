from __future__ import annotations

import json

import pytest

from core.demo_autonomy_authorization import DemoAutonomyAuthorizationStore
from core.operational_runtime import build_operational_runtime


def test_demo_autonomy_defaults_disabled(tmp_path):
    store = DemoAutonomyAuthorizationStore(tmp_path / "demo-autonomy.json")
    assert store.state.enabled is False
    assert store.state.amount is None
    assert store.state.duration_seconds is None


def test_demo_autonomy_enable_disable_is_durable(tmp_path):
    path = tmp_path / "demo-autonomy.json"
    store = DemoAutonomyAuthorizationStore(path)
    enabled = store.enable(
        amount=0.01,
        duration_seconds=60,
        authorized_at="2026-09-24T00:00:00+00:00",
        authorized_by="user",
    )
    assert enabled.enabled is True
    restored = DemoAutonomyAuthorizationStore(path)
    assert restored.state.enabled is True
    assert restored.state.amount == 0.01
    assert restored.state.duration_seconds == 60
    assert restored.state.authorized_by == "user"
    disabled = restored.disable()
    assert disabled.enabled is False
    assert DemoAutonomyAuthorizationStore(path).state.enabled is False


@pytest.mark.parametrize(
    "payload",
    [
        {"enabled": True, "amount": -1, "duration_seconds": 60, "authorized_at": "x", "authorized_by": "user"},
        {"enabled": True, "amount": 0.01, "duration_seconds": 0, "authorized_at": "x", "authorized_by": "user"},
        {"enabled": True, "amount": 0.01, "duration_seconds": 60, "authorized_at": "", "authorized_by": "user"},
    ],
)
def test_corrupt_or_invalid_authority_fails_closed(tmp_path, payload):
    path = tmp_path / "demo-autonomy.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert DemoAutonomyAuthorizationStore(path).state.enabled is False


def test_runtime_owns_separate_demo_autonomy_authority(tmp_path):
    runtime = build_operational_runtime(tmp_path)
    assert runtime.demo_autonomy.state.enabled is False
    assert runtime.preferences if hasattr(runtime, "preferences") else True
