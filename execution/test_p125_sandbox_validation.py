import pytest

from execution.p123_broker_order import BrokerOrderBoundary
from execution.p125_sandbox_validation import SandboxScenario, SandboxValidationBoundary
from core.models import Signal


def request(request_id="req-125"):
    return BrokerOrderBoundary.from_signal(
        request_id=request_id,
        symbol="EURUSD",
        signal=Signal.COMPRA,
        amount=10,
        duration_seconds=60,
    )


def test_accept_gets_external_id_and_duplicate_is_blocked():
    result = SandboxValidationBoundary().run(request(), SandboxScenario.ACCEPT)
    assert result.accepted is True
    assert result.external_id is not None
    assert result.duplicate_blocked is True


def test_rejection_is_not_executed():
    result = SandboxValidationBoundary().run(request("req-reject"), SandboxScenario.REJECT)
    assert result.accepted is False
    assert result.external_status.value == "NOT_EXECUTED"


def test_unknown_acceptance_remains_ambiguous():
    result = SandboxValidationBoundary().run(request("req-unknown"), SandboxScenario.UNKNOWN)
    assert result.accepted is True
    assert result.external_id is None
    assert result.external_status.value == "UNKNOWN"


def test_disconnect_fails_closed():
    result = SandboxValidationBoundary().run(request("req-disconnect"), SandboxScenario.DISCONNECTED)
    assert result.accepted is False
    assert result.external_status.value == "NOT_EXECUTED"


@pytest.mark.parametrize("scenario", list(SandboxScenario))
def test_all_scenarios_are_deterministic(scenario):
    first = SandboxValidationBoundary().run(request(f"req-{scenario.value}-1"), scenario)
    second = SandboxValidationBoundary().run(request(f"req-{scenario.value}-1"), scenario)
    assert first == second
