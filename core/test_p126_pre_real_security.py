from core.models import Signal
from core.p126_pre_real_security import PreRealSecurityValidator
from core.runtime_config import RuntimeConfig
from execution.p123_broker_order import BrokerOrderBoundary
from execution.p124_broker_session import BrokerSessionObservation, BrokerSessionStatus
from execution.p125_sandbox_validation import SandboxScenario, SandboxValidationBoundary


def test_pre_real_checklist_passes_with_safe_defaults():
    config = RuntimeConfig("EURUSD", "1m", 10, 60)
    session = BrokerSessionObservation(BrokerSessionStatus.UNAVAILABLE, "not connected")
    request = BrokerOrderBoundary.from_signal(
        request_id="p126", symbol="EURUSD", signal=Signal.COMPRA, amount=10, duration_seconds=60
    )
    sandbox = SandboxValidationBoundary().run(request, SandboxScenario.UNKNOWN)

    result = PreRealSecurityValidator.validate(config, session, sandbox)

    assert result.config_safe is True
    assert result.session_safe is True
    assert result.sandbox_safe is True
    assert result.passed is True


def test_authenticated_session_does_not_pass_pre_real_gate():
    config = RuntimeConfig("EURUSD", "1m", 10, 60)
    session = BrokerSessionObservation(BrokerSessionStatus.AUTHENTICATED, "connected")
    request = BrokerOrderBoundary.from_signal(
        request_id="p126-auth", symbol="EURUSD", signal=Signal.COMPRA, amount=10, duration_seconds=60
    )
    sandbox = SandboxValidationBoundary().run(request, SandboxScenario.UNKNOWN)

    result = PreRealSecurityValidator.validate(config, session, sandbox)
    assert result.passed is False
