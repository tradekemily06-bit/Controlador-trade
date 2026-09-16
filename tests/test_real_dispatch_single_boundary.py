from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ALLOWED_ORDER_SEND = ROOT / "execution" / "icmarkets_mt5_demo_adapter.py"
REAL_GATEWAY = ROOT / "execution" / "real_gateway.py"
ADAPTER_GATEWAY = ROOT / "execution" / "adapter_gateway.py"
LEDGER = ROOT / "execution" / "execution_ledger.py"


def _runtime_python_files() -> list[Path]:
    files: list[Path] = []
    for directory in (ROOT / "execution", ROOT / "integration", ROOT / "core", ROOT / "security"):
        files.extend(path for path in directory.rglob("*.py") if not path.name.startswith("test_"))
    files.append(ROOT / "app.py")
    return files


def _calls_with_attribute(path: Path, attribute: str) -> list[ast.Call]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == attribute
    ]


def test_order_send_exists_only_inside_the_broker_adapter() -> None:
    violations: list[str] = []
    for path in _runtime_python_files():
        for node in _calls_with_attribute(path, "order_send"):
            if path.resolve() != ALLOWED_ORDER_SEND.resolve():
                violations.append(f"{path.relative_to(ROOT)}:{node.lineno}")
    assert not violations, "direct broker order_send bypass found outside the official adapter: " + ", ".join(sorted(violations))


def test_real_gateway_construction_is_not_replicated_outside_execution_boundary() -> None:
    violations: list[str] = []
    for path in _runtime_python_files():
        if path.resolve() == REAL_GATEWAY.resolve():
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "RealExecutionGateway":
                violations.append(f"{path.relative_to(ROOT)}:{node.lineno}")
    assert not violations, "REAL gateway construction bypass found outside execution/real_gateway.py: " + ", ".join(sorted(violations))


def test_broker_adapter_gateway_is_only_composed_by_real_gateway() -> None:
    violations: list[str] = []
    for path in _runtime_python_files():
        if path.resolve() == REAL_GATEWAY.resolve():
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "BrokerAdapterGateway":
                violations.append(f"{path.relative_to(ROOT)}:{node.lineno}")
    assert not violations, "broker adapter gateway composition bypass found outside execution/real_gateway.py: " + ", ".join(sorted(violations))


def test_adapter_execute_is_only_called_by_the_broker_boundary() -> None:
    """Broker adapters must not become callable execution ports by accident."""
    violations: list[str] = []
    for path in _runtime_python_files():
        if path.resolve() == ADAPTER_GATEWAY.resolve():
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute) or node.func.attr != "execute":
                continue
            receiver = node.func.value
            if isinstance(receiver, ast.Name) and receiver.id == "adapter":
                violations.append(f"{path.relative_to(ROOT)}:{node.lineno}")
            elif isinstance(receiver, ast.Attribute) and receiver.attr in {"_adapter", "adapter"}:
                violations.append(f"{path.relative_to(ROOT)}:{node.lineno}")
    assert not violations, "direct broker adapter execution bypass found: " + ", ".join(sorted(violations))


def test_ledger_mutations_are_only_called_by_execution_boundaries() -> None:
    """Ledger state changes must remain behind the execution/reconciliation boundaries."""
    allowed = {REAL_GATEWAY.resolve(), ROOT / "execution" / "gateway.py"}
    mutators = {"reserve", "record", "mark_accepted", "mark_rejected", "mark_unknown", "reconcile"}
    violations: list[str] = []
    for path in _runtime_python_files():
        if path.resolve() in allowed:
            continue
        for attribute in mutators:
            for node in _calls_with_attribute(path, attribute):
                receiver = node.func.value
                if isinstance(receiver, ast.Attribute) and receiver.attr == "ledger":
                    violations.append(f"{path.relative_to(ROOT)}:{node.lineno}:{attribute}")
    assert not violations, "direct execution-ledger mutation bypass found: " + ", ".join(sorted(violations))


def test_ledger_implementation_is_not_constructed_as_a_side_channel() -> None:
    """A runtime component may share the canonical ledger, but not create a second one."""
    allowed = {ROOT / "core" / "operational_runtime.py"}
    violations: list[str] = []
    for path in _runtime_python_files():
        if path.resolve() == LEDGER.resolve() or path.resolve() in allowed:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "ExecutionLedger":
                violations.append(f"{path.relative_to(ROOT)}:{node.lineno}")
    assert not violations, "side-channel ExecutionLedger construction found: " + ", ".join(sorted(violations))
