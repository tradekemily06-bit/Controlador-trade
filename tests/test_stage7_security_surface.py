from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_demo_gateway_is_explicitly_demo_only():
    source = _read("execution/gateway.py")
    assert 'class ExecutionGateway' in source
    assert 'if request.mode is not ExecutionMode.DEMO:' in source
    assert 'P5 aceita somente execução DEMO/PAPER' in source
    # The source must not contain a REAL dispatch branch in this legacy/demo gateway.
    assert 'request.mode is ExecutionMode.REAL' not in source


def test_real_gateway_requires_active_authorization_and_admission():
    source = _read("execution/real_gateway.py")
    assert "authorization.active" in source
    assert "admission.admitted" in source
    assert "request.mode is not ExecutionMode.REAL" in source
    assert "_global_barrier_error" in source
    assert "_revalidate_risk" in source
    assert "_revalidate_safety" in source


def test_broker_registry_does_not_publicly_expose_executable_adapter():
    source = _read("execution/broker_registry.py")
    assert "_BROKER_GATEWAY_CAPABILITY = object()" in source
    assert "def _get_for_gateway" in source
    assert "capability is not _BROKER_GATEWAY_CAPABILITY" in source


def test_demo_remote_bridge_cannot_dispatch_real():
    source = _read("execution/remote_mt5_bridge.py")
    assert "ExecutionMode.DEMO" in source
    assert "execute_demo" in source
    # This bridge exposes only the demo operation; absence of a REAL branch is intentional.
    assert "ExecutionMode.REAL" not in source


def test_default_demo_factory_does_not_return_a_raw_broker_adapter():
    source = _read("execution/default_registry.py")
    assert "build_ic_markets_mt5_demo_gateway" in source
    assert "build_ic_markets_mt5_demo_port" in source
    assert "return runtime.gateway" in source
    assert "return build_ic_markets_mt5_demo_port" not in source


def test_real_authorization_defaults_to_disabled():
    source = _read("core/p112_real_execution_contract.py")
    assert "explicitly_enabled: bool = False" in source
    assert "real_execution_allowed: bool = False" in source
    assert "if self.real_execution_allowed and not self.explicitly_enabled" in source


def test_legacy_execution_surfaces_are_not_allowed_to_create_real_authority():
    # The repository has accumulated historical P-series modules. This guard keeps
    # legacy compatibility from silently becoming a second REAL authority source.
    for path in sorted((ROOT / "core").glob("p*.py")):
        text = path.read_text(encoding="utf-8")
        if "RealExecutionAuthorization" not in text:
            continue
        # P112 owns the immutable authorization contract; P117 consumes that
        # contract only as an input and never creates authority itself.
        if path.name == "p112_real_execution_contract.py":
            assert "_issue_real_authorization" in text
            continue
        if path.name == "p117_real_admission.py":
            assert "RealAdmissionBoundary" in text
            assert "_provenance_token" in text
            assert "_ADMITTED_PROVENANCE" in text
            continue
        assert "_issue_real_authorization" not in text, path
