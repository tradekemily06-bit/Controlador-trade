from __future__ import annotations

from pathlib import Path

from core.models import Signal
from core.p112_real_execution_contract import RealExecutionAuthorization
from core.p114_real_safety_gate import RealSafetyGate
from core.p117_real_admission import RealAdmissionBoundary
from execution.adapter_gateway import BrokerAdapterGateway
from execution.broker_registry import BrokerRegistry
from execution.execution_ledger import ExecutionLedger
from execution.execution_lifecycle import ExecutionLifecycleStore
from execution.execution_lifecycle import ExecutionLifecycleState
from execution.ports import ExecutionMode, ExecutionResult
from execution.real_gateway import RealExecutionGateway, RealGatewayStatus
from integration.persistent_broker_connection import PersistentBrokerConnectionRuntime
from integration.real_execution_runtime import RealExecutionRuntime


class FakeAdapter:
    def __init__(self, available=True):
        self.available = available
        self.calls = 0

    def is_available(self):
        return self.available

    def execute(self, request):
        self.calls += 1
        return ExecutionResult(True, "accepted", external_id="ext-1")


def build_runtime(tmp_path: Path, *, real_enabled=False, available=True):
    adapter = FakeAdapter(available)
    connection = PersistentBrokerConnectionRuntime(adapter, poll_seconds=0.01)
    registry = BrokerRegistry()
    registry.register("fake", adapter)
    gateway = RealExecutionGateway(
        BrokerAdapterGateway(registry),
        ExecutionLedger(tmp_path / "ledger.json"),
        ExecutionLifecycleStore(tmp_path / "lifecycle.json"),
    )
    runtime = RealExecutionRuntime(
        broker_id="fake",
        adapter_id="fake-adapter",
        broker_connection=connection,
        gateway=gateway,
        ledger=ExecutionLedger(tmp_path / "ledger-runtime.json"),
        lifecycle=ExecutionLifecycleStore(tmp_path / "lifecycle-runtime.json"),
        real_enabled=real_enabled,
        audit_verified=True,
        recovery_safe=lambda: True,
        market_healthy=lambda: True,
        risk_approved=lambda: True,
        kill_switch_clear=lambda: True,
    )
    return runtime, connection, adapter


def test_real_runtime_requires_explicit_phrase(tmp_path):
    runtime, connection, adapter = build_runtime(tmp_path, real_enabled=True)
    connection.start()
    runtime.select_mode(ExecutionMode.REAL)
    try:
        try:
            runtime.request_confirmation(request_id="r1", phrase="CONFIRMO")
        except ValueError as exc:
            assert "CONFIRMO REAL" in str(exc)
        else:
            raise AssertionError("confirmation should reject wrong phrase")
        assert adapter.calls == 0
    finally:
        connection.user_disconnect()


def test_real_runtime_confirmation_is_one_shot(tmp_path):
    runtime, connection, adapter = build_runtime(tmp_path, real_enabled=True)
    connection.start()
    runtime.select_mode(ExecutionMode.REAL)
    try:
        confirmation = runtime.request_confirmation(request_id="r1", phrase="CONFIRMO REAL")
        result = runtime.execute_confirmed(
            request_id="r1",
            symbol="EURUSD",
            signal=Signal.COMPRA,
            amount=0.01,
            duration_seconds=60,
            confirmation_id=confirmation.confirmation_id,
        )
        assert result.status is RealGatewayStatus.ADMITTED
        assert adapter.calls == 1
        replay = runtime.execute_confirmed(
            request_id="r1",
            symbol="EURUSD",
            signal=Signal.COMPRA,
            amount=0.01,
            duration_seconds=60,
            confirmation_id=confirmation.confirmation_id,
        )
        assert replay.status is RealGatewayStatus.BLOCKED
        assert adapter.calls == 1
    finally:
        connection.user_disconnect()


def test_user_disconnect_blocks_real_before_gateway(tmp_path):
    runtime, connection, adapter = build_runtime(tmp_path, real_enabled=True)
    runtime.start()
    runtime.select_mode(ExecutionMode.REAL)
    connection.user_disconnect()
    confirmation = runtime.request_confirmation(request_id="r2", phrase="CONFIRMO REAL")
    result = runtime.execute_confirmed(
        request_id="r2",
        symbol="EURUSD",
        signal=Signal.VENDA,
        amount=0.01,
        duration_seconds=60,
        confirmation_id=confirmation.confirmation_id,
    )
    assert result.status is RealGatewayStatus.BLOCKED
    assert adapter.calls == 0


def test_real_disabled_never_reaches_adapter(tmp_path):
    runtime, connection, adapter = build_runtime(tmp_path, real_enabled=False)
    runtime.start()
    runtime.select_mode(ExecutionMode.REAL)
    confirmation = runtime.request_confirmation(request_id="r3", phrase="CONFIRMO REAL")
    try:
        result = runtime.execute_confirmed(
            request_id="r3",
            symbol="EURUSD",
            signal=Signal.COMPRA,
            amount=0.01,
            duration_seconds=60,
            confirmation_id=confirmation.confirmation_id,
        )
        assert result.status is RealGatewayStatus.BLOCKED
        assert adapter.calls == 0
    finally:
        connection.user_disconnect()
