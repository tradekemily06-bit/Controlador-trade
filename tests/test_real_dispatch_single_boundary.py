from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ALLOWED_ORDER_SEND = ROOT / "execution" / "icmarkets_mt5_demo_adapter.py"
REAL_GATEWAY = ROOT / "execution" / "real_gateway.py"
ADAPTER_GATEWAY = ROOT / "execution" / "adapter_gateway.py"
DEMO_GATEWAY_FACTORY = ROOT / "execution" / "default_registry.py"
REGISTRY = ROOT / "execution" / "broker_registry.py"
LEDGER = ROOT / "execution" / "execution_ledger.py"
EXECUTION_BOUNDARIES = {
    ROOT / "execution" / "gateway.py",
    ADAPTER_GATEWAY,
    REAL_GATEWAY,
    ALLOWED_ORDER_SEND,
}


def _runtime_python_files() -> list[Path]:
    files: list[Path] = []
    for directory in (ROOT / "execution", ROOT / "integration", ROOT / "core", ROOT / "security"):
        files.extend(path for path in directory.rglob("*.py") if not path.name.startswith("test_"))
    files.append(ROOT / "app.py")
    return files


def _tree(path: Path) -> ast.AST:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _calls_with_attribute(path: Path, attribute: str) -> list[ast.Call]:
    tree = _tree(path)
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


def test_mt5_trade_mutations_stay_at_broker_edge() -> None:
    trade_calls = {"order_check", "order_send", "order_modify", "order_delete", "order_close_by"}
    violations: list[str] = []
    for path in _runtime_python_files():
        if path.resolve() == ALLOWED_ORDER_SEND.resolve():
            continue
        for attribute in trade_calls:
            for node in _calls_with_attribute(path, attribute):
                violations.append(f"{path.relative_to(ROOT)}:{node.lineno}:{attribute}")
    assert not violations, "MT5 trade operation found outside the broker edge: " + ", ".join(sorted(violations))


def test_real_gateway_construction_is_not_replicated_outside_execution_boundary() -> None:
    violations: list[str] = []
    for path in _runtime_python_files():
        if path.resolve() == REAL_GATEWAY.resolve():
            continue
        for node in ast.walk(_tree(path)):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "RealExecutionGateway":
                violations.append(f"{path.relative_to(ROOT)}:{node.lineno}")
    assert not violations, "REAL gateway construction bypass found outside execution/real_gateway.py: " + ", ".join(sorted(violations))


def test_broker_adapter_gateway_is_only_composed_by_real_gateway() -> None:
    violations: list[str] = []
    for path in _runtime_python_files():
        if path.resolve() == REAL_GATEWAY.resolve():
            continue
        for node in ast.walk(_tree(path)):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "BrokerAdapterGateway":
                violations.append(f"{path.relative_to(ROOT)}:{node.lineno}")
    assert not violations, "broker adapter gateway composition bypass found outside execution/real_gateway.py: " + ", ".join(sorted(violations))


def test_registry_has_no_public_adapter_get_or_mapping_escape_hatch() -> None:
    violations: list[str] = []
    for path in _runtime_python_files():
        if path.resolve() == REGISTRY.resolve():
            continue
        tree = _tree(path)
        aliases: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
                call = node.value
                is_registry = isinstance(call.func, ast.Name) and call.func.id == "BrokerRegistry"
                is_registry = is_registry or (isinstance(call.func, ast.Attribute) and call.func.attr == "BrokerRegistry")
                if is_registry:
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            aliases.add(target.id)
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Name) and node.value.id in aliases:
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        aliases.add(target.id)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            receiver = node.func.value
            if isinstance(receiver, ast.Name) and receiver.id in aliases and node.func.attr in {"get", "as_mapping"}:
                violations.append(f"{path.relative_to(ROOT)}:{node.lineno}:{node.func.attr}")
        if path.resolve() != DEMO_GATEWAY_FACTORY.resolve():
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "_get_for_gateway":
                    violations.append(f"{path.relative_to(ROOT)}:{node.lineno}:_get_for_gateway")
    assert not violations, "broker registry adapter escape hatch found: " + ", ".join(sorted(violations))


def test_broker_gateway_capability_is_imported_only_at_execution_boundary() -> None:
    violations: list[str] = []
    for path in _runtime_python_files():
        if path.resolve() in {REGISTRY.resolve(), ADAPTER_GATEWAY.resolve(), DEMO_GATEWAY_FACTORY.resolve()}:
            continue
        for node in ast.walk(_tree(path)):
            if isinstance(node, ast.ImportFrom) and node.module == "execution.broker_registry":
                if any(alias.name == "_BROKER_GATEWAY_CAPABILITY" for alias in node.names):
                    violations.append(f"{path.relative_to(ROOT)}:{node.lineno}")
    assert not violations, "broker gateway capability leaked outside execution composition boundaries: " + ", ".join(sorted(violations))


def test_adapter_execute_is_only_called_by_execution_boundaries() -> None:
    violations: list[str] = []
    for path in _runtime_python_files():
        if path.resolve() in EXECUTION_BOUNDARIES:
            continue
        for node in _calls_with_attribute(path, "execute"):
            receiver = node.func.value
            if isinstance(receiver, ast.Name) and receiver.id in {"adapter", "_adapter", "broker", "executor", "_executor"}:
                violations.append(f"{path.relative_to(ROOT)}:{node.lineno}")
            elif isinstance(receiver, ast.Attribute) and receiver.attr in {"adapter", "_adapter", "broker", "executor", "_executor"}:
                violations.append(f"{path.relative_to(ROOT)}:{node.lineno}")
    assert not violations, "direct adapter/executor execution bypass found: " + ", ".join(sorted(violations))


def test_http_application_never_constructs_or_calls_an_executor() -> None:
    tree = _tree(ROOT / "app.py")
    violations: list[str] = []
    forbidden_imports = {
        "execution.real_gateway",
        "execution.adapter_gateway",
        "execution.icmarkets_mt5_demo_adapter",
        "execution.broker_registry",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module in forbidden_imports:
            violations.append(f"app.py:{node.lineno}:import {node.module}")
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "execute":
            violations.append(f"app.py:{node.lineno}:execute")
    assert not violations, "HTTP application reaches an execution implementation directly: " + ", ".join(violations)


def test_ledger_mutations_are_only_called_by_execution_boundaries() -> None:
    allowed = {REAL_GATEWAY.resolve(), ROOT / "execution" / "gateway.py"}
    mutators = {"reserve", "record", "mark_accepted", "mark_rejected", "mark_unknown", "reconcile"}
    violations: list[str] = []
    for path in _runtime_python_files():
        if path.resolve() in allowed:
            continue
        tree = _tree(path)
        ledger_names: set[str] = {"ledger", "_ledger", "execution_ledger"}
        aliases: set[str] = set(ledger_names)
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Attribute) and node.value.attr in ledger_names:
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        aliases.add(target.id)
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Name) and node.value.id in aliases:
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        aliases.add(target.id)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in mutators:
                receiver = node.func.value
                if isinstance(receiver, ast.Name) and receiver.id in aliases:
                    violations.append(f"{path.relative_to(ROOT)}:{node.lineno}:{node.func.attr}")
                elif isinstance(receiver, ast.Attribute) and receiver.attr in ledger_names:
                    violations.append(f"{path.relative_to(ROOT)}:{node.lineno}:{node.func.attr}")
    assert not violations, "execution-ledger mutation bypass found through direct receiver or alias: " + ", ".join(sorted(violations))


def test_ledger_implementation_is_not_constructed_as_a_side_channel() -> None:
    allowed = {ROOT / "core" / "operational_runtime.py"}
    violations: list[str] = []
    for path in _runtime_python_files():
        if path.resolve() == LEDGER.resolve() or path.resolve() in allowed:
            continue
        for node in ast.walk(_tree(path)):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "ExecutionLedger":
                violations.append(f"{path.relative_to(ROOT)}:{node.lineno}")
    assert not violations, "side-channel ExecutionLedger construction found: " + ", ".join(sorted(violations))


def test_execution_mode_environment_is_read_only_at_application_composition_boundary() -> None:
    violations: list[str] = []
    allowed_files = {ROOT / "app.py", ROOT / "core" / "operational_runtime.py"}
    for path in _runtime_python_files():
        if path.resolve() in allowed_files:
            continue
        text = path.read_text(encoding="utf-8")
        if "CONTROLADOR_EXECUTION_PROVIDER" in text or "CONTROLADOR_EXECUTION_MODE" in text:
            violations.append(str(path.relative_to(ROOT)))
    assert not violations, "execution-mode environment is interpreted outside the composition boundary: " + ", ".join(sorted(violations))
