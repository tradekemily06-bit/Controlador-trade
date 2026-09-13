from core.operational_alerts import build_operational_incidents


def _healthy_observability() -> dict:
    return {
        "execution": {"state": "READY_DEMO"},
        "recovery": {"state": "SAFE_TO_RESUME"},
        "reconciliation": {"pending_request_ids": [], "unknown_request_ids": []},
        "kill_switch": {"enabled": False},
        "runtime_health": {"state": "HEALTHY"},
        "market_data": {"health": "HEALTHY"},
    }


def test_healthy_runtime_has_no_incidents():
    assert build_operational_incidents(_healthy_observability()) == []


def test_invalid_market_data_is_critical():
    data = _healthy_observability()
    data["market_data"] = {"health": "INVALID"}

    incidents = build_operational_incidents(data)

    assert [(item.code, item.severity) for item in incidents] == [("MARKET_DATA_UNSAFE", "CRITICAL")]


def test_stale_market_data_is_warning():
    data = _healthy_observability()
    data["market_data"] = {"health": "STALE"}

    incidents = build_operational_incidents(data)

    assert [(item.code, item.severity) for item in incidents] == [("MARKET_DATA_DEGRADED", "WARNING")]


def test_blocked_execution_and_reconciliation_are_reported_without_side_effects():
    data = _healthy_observability()
    data["execution"] = {"state": "BLOCKED"}
    data["recovery"] = {"state": "REQUIRES_RECONCILIATION"}
    data["reconciliation"] = {"pending_request_ids": ["req-1"], "unknown_request_ids": []}

    incidents = build_operational_incidents(data)
    codes = {item.code for item in incidents}

    assert "EXECUTION_BLOCKED" in codes
    assert "RECONCILIATION_REQUIRED" in codes
    assert "EXECUTION_RECONCILIATION_PENDING" in codes
    assert all(item.severity in {"CRITICAL", "WARNING"} for item in incidents)


def test_invalid_input_fails_closed():
    incidents = build_operational_incidents(None)  # type: ignore[arg-type]

    assert len(incidents) == 1
    assert incidents[0].code == "OPERATIONAL_INPUT_INVALID"
    assert incidents[0].severity == "CRITICAL"
