from datetime import datetime, timezone
from pathlib import Path

from core.kill_switch import KillSwitch
from execution.gateway import ExecutionGateway, GatewayStatus
from execution.paper import PaperExecutor
from execution.ports import ExecutionMode, ExecutionRequest
from core.models import Signal


FINGERPRINT_A = "a" * 64
FINGERPRINT_B = "b" * 64


def request(fingerprint=FINGERPRINT_A):
    return ExecutionRequest(
        symbol="EURUSD",
        signal=Signal.COMPRA,
        amount=0.01,
        duration_seconds=60,
        mode=ExecutionMode.DEMO,
        request_id="identity-test",
        market_data_fingerprint=fingerprint,
    )


def test_fingerprinted_request_requires_authoritative_provider():
    gateway = ExecutionGateway(PaperExecutor(), KillSwitch())
    result = gateway.execute("identity-test-1", request())
    assert result.status is GatewayStatus.BLOCKED
    assert "identidade" in result.message


def test_fingerprinted_request_blocks_when_runtime_identity_changes():
    current = FINGERPRINT_A
    gateway = ExecutionGateway(
        PaperExecutor(),
        KillSwitch(),
        market_data_fingerprint_provider=lambda: current,
    )
    first = gateway.execute("identity-test-2", request())
    assert first.status is GatewayStatus.ACCEPTED

    current = FINGERPRINT_B
    second = gateway.execute("identity-test-3", request())
    assert second.status is GatewayStatus.BLOCKED
    assert "mudaram" in second.message


def test_fingerprinted_request_blocks_when_runtime_identity_disappears():
    gateway = ExecutionGateway(
        PaperExecutor(),
        KillSwitch(),
        market_data_fingerprint_provider=lambda: None,
    )
    result = gateway.execute("identity-test-4", request())
    assert result.status is GatewayStatus.BLOCKED
    assert "snapshot" in result.message
