from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_public_app_is_explicitly_demo_only() -> None:
    app = _read("app.py")
    assert "build_demo_execution_port" in app
    assert "RealExecutionGateway(" not in app
    assert "order_send(" not in app


def test_operational_runtime_does_not_construct_real_gateway() -> None:
    runtime = _read("core/operational_runtime.py")
    assert "RealExecutionGateway(" not in runtime
    assert "build_demo_execution_port" not in runtime


def test_real_gateway_is_not_constructed_by_integration_layers() -> None:
    integration_root = ROOT / "integration"
    for path in integration_root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "RealExecutionGateway(" not in text, f"REAL gateway constructed outside its explicit boundary: {path}"


def test_real_authorization_cannot_be_enabled_implicitly() -> None:
    contract = _read("core/p112_real_execution_contract.py")
    assert "if self.real_execution_allowed and not self.explicitly_enabled" in contract
    assert "self.explicitly_enabled and self.real_execution_allowed" in contract
