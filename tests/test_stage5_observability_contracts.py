from __future__ import annotations

from core.observability_redaction import REDACTED, redact, redact_event
from core.p21_observability import HealthState


def test_redaction_recurses_without_mutating_input():
    original = {
        "request_id": "req-1",
        "authorization": "Bearer secret-token",
        "nested": {"api_key": "abc", "symbol": "EURUSD"},
        "items": [{"password": "pw", "value": 3}],
    }

    safe = redact(original)

    assert safe["authorization"] == REDACTED
    assert safe["nested"]["api_key"] == REDACTED
    assert safe["items"][0]["password"] == REDACTED
    assert safe["nested"]["symbol"] == "EURUSD"
    assert original["authorization"] == "Bearer secret-token"


def test_event_boundary_requires_type_and_mapping():
    event = redact_event(event_type="EXECUTION_BLOCKED", payload={"token": "hidden", "reason": "kill-switch"})
    assert event["event_type"] == "EXECUTION_BLOCKED"
    assert event["payload"]["token"] == REDACTED


def test_health_states_are_observational_not_authorization_states():
    assert {HealthState.HEALTHY.value, HealthState.ATTENTION.value, HealthState.BLOCKED.value} == {
        "HEALTHY",
        "ATTENTION",
        "BLOCKED",
    }
