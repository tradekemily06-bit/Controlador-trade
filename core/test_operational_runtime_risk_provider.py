from core.operational_runtime import build_operational_runtime


def test_runtime_wires_authoritative_risk_provider(tmp_path):
    expected = "a" * 64
    runtime = build_operational_runtime(tmp_path, risk_state_fingerprint_provider=lambda: expected)
    assert runtime.gateway._risk_state_fingerprint_provider() == expected


def test_runtime_without_risk_source_does_not_fabricate_identity(tmp_path):
    runtime = build_operational_runtime(tmp_path)
    assert runtime.gateway._risk_state_fingerprint_provider is None
