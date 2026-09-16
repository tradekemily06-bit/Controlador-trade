from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ALLOWED_ORDER_SEND = ROOT / "execution" / "icmarkets_mt5_demo_adapter.py"
REAL_GATEWAY = ROOT / "execution" / "real_gateway.py"
ADAPTER_GATEWAY = ROOT / "execution" / "adapter_gateway.py"
DEMO_GATEWAY_FACTORY = ROOT / "execution" / "default_registry.py"
DEMO_BROKER_PORT = ROOT / "execution" / "demo_broker_port.py"
REGISTRY = ROOT / "execution" / "broker_registry.py"
LEDGER = ROOT / "execution" / "execution_ledger.py"
EXECUTION_BOUNDARIES = {
    ROOT / "execution" / "gateway.py",
    ADAPTER_GATEWAY,
    REAL_GATEWAY,
    ALLOWED_ORDER_SEND,
    DEMO_BROKER_PORT,
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
    return [node for node in ast.walk(_tree(path)) if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == attribute]


def test_order_send_exists_only_inside_the_broker_adapter() -> None:
    violations = []
    for path in _runtime_python_files():
        for node in _calls_with_attribute(path, "order_send"):
            if path.resolve() != ALLOWED_ORDER_SEND.resolve():
                violations.append(f"{path.relative_to(ROOT)}:{node.lineno}")
    assert not violations, "direct broker order_send bypass found outside the official adapter: " + ", ".join(sorted(violations))


def test_mt5_trade_mutations_stay_at_broker_edge() -> None:
    trade_calls = {"order_check", "order_send", "order_modify", "order_delete", "order_close_by"}
    violations = []
    for path in _runtime_python_files():
        if path.resolve() == ALLOWED_ORDER_SEND.resolve():
            continue
        for attribute in trade_calls:
            for node in _calls_with_attribute(path, attribute):
                violations.append(f"{path.relative_to(ROOT)}:{node.lineno}:{attribute}")
    assert not violations, "MT5 trade operation found outside the broker edge: " + ", ".join(sorted(violations))


def test_real_gateway_construction_is_not_replicated_outside_execution_boundary() -> None:
    violations = []
    for path in _runtime_python_files():
        if path.resolve() == REAL_GATEWAY.resolve():
            continue
        for node in ast.walk(_tree(path)):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "RealExecutionGateway":
                violations.append(f"{path.relative_to(ROOT)}:{node.lineno}")
    assert not violations, "REAL gateway construction bypass found outside execution/real_gateway.py: " + ", ".join(sorted(violations))


def test_broker_adapter_gateway_is_only_composed_by_real_gateway() -> None:
    violations = []
    for path in _runtime_python_files():
        if path.resolve() == REAL_GATEWAY.resolve():
            continue
        for node in ast.walk(_tree(path)):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "BrokerAdapterGateway":
                violations.append(f"{path.relative_to(ROOT)}:{node.lineno}")
    assert not violations, "broker adapter gateway composition bypass found outside execution/real_gateway.py: " + ", ".join(sorted(violations))


def test_registry_has_no_public_adapter_get_or_mapping_escape_hatch() -> None:
    violations = []
    allowed_lookup_files = {DEMO_GATEWAY_FACTORY.resolve(), ADAPTER_GATEWAY.resolve()}
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
        if path.resolve() not in allowed_lookup_files:
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "_get_for_gateway":
                    violations.append(f"{path.relative_to(ROOT)}:{node.lineno}:_get_for_gateway")
    assert not violations, "broker registry adapter escape hatch found: " + ", ".join(sorted(violations))


def test_broker_gateway_capability_is_imported_only_at_execution_boundary() -> None:
    violations = []
    for path in _runtime_python_files():
        if path.resolve() in {REGISTRY.resolve(), ADAPTER_GATEWAY.resolve(), DEMO_GATEWAY_FACTORY.resolve()}:
            continue
        for node in ast.walk(_tree(path)):
            if isinstance(node, ast.ImportFrom) and node.module == "execution.broker_registry" and any(alias.name == "_BROKER_GATEWAY_CAPABILITY" for alias in node.names):
                violations.append(f"{path.relative_to(ROOT)}:{node.lineno}")
    assert not violations, "broker gateway capability leaked outside execution composition boundaries: " + ", ".join(sorted(violations))


def test_concrete_broker_adapter_is_not_imported_outside_execution_boundary() -> None:
    violations = []
    allowed = {ALLOWED_ORDER_SEND.resolve(), DEMO_GATEWAY_FACTORY.resolve(), DEMO_BROKER_PORT.resolve()}
    for path in _runtime_python_files():
        if path.resolve() in allowed:
            continue
        for node in ast.walk(_tree(path)):
            if isinstance(node, ast.ImportFrom) and node.module == "execution.icmarkets_mt5_demo_adapter":
                violations.append(f"{path.relative_to(ROOT)}:{node.lineno}")
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "execution.icmarkets_mt5_demo_adapter":
                        violations.append(f"{path.relative_to(ROOT)}:{node.lineno}")
    assert not violations, "concrete broker adapter import leaked outside execution boundary: " + ", ".join(sorted(violations))


def test_adapter_execute_is_only_called_by_execution_boundaries() -> None:
    violations = []
    forbidden_names = {"adapter", "_adapter", "broker", "executor", "_executor"}
    for path in _runtime_python_files():
        if path.resolve() in EXECUTION_BOUNDARIES:
            continue
        tree = _tree(path)
        aliases: set[str] = set(forbidden_names)
        changed = True
        while changed:
            changed = False
            for node in ast.walk(tree):
                if not isinstance(node, ast.Assign):
                    continue
                value = node.value
                source_name = value.id if isinstance(value, ast.Name) else None
                source_attr = value.attr if isinstance(value, ast.Attribute) else None
                if source_name in aliases or source_attr in forbidden_names:
                    for target in node.targets:
                        if isinstance(target, ast.Name) and target.id not in aliases:
                            aliases.add(target.id)
                            changed = True
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute) or node.func.attr != "execute":
                continue
            receiver = node.func.value
            if isinstance(receiver, ast.Name) and receiver.id in aliases:
                violations.append(f"{path.relative_to(ROOT)}:{node.lineno}")
            elif isinstance(receiver, ast.Attribute) and receiver.attr in forbidden_names:
                violations.append(f"{path.relative_to(ROOT)}:{node.lineno}")
    assert not violations, "direct adapter/executor execution bypass found: " + ", ".join(sorted(violations))


def test_imported_execution_objects_cannot_execute_outside_execution_boundary() -> None:
    """Catch renamed/imported executor objects that evade name-based alias checks."""
    violations = []
    execution_symbols = {
        "ExecutionGateway", "RealExecutionGateway", "BrokerAdapterGateway",
        "PaperExecutor", "ExecutionPort", "BrokerAdapter", "ICMarketsMT5DemoAdapter",
    }
    for path in _runtime_python_files():
        if path.resolve() in EXECUTION_BOUNDARIES:
            continue
        tree = _tree(path)
        imported = set()
        for node in tree.body:
            if isinstance(node, ast.ImportFrom) and isinstance(node.module, str) and node.module.startswith("execution."):
                for alias in node.names:
                    if alias.name in execution_symbols:
                        imported.add(alias.asname or alias.name)
        if not imported:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute) or node.func.attr != "execute":
                continue
            receiver = node.func.value
            direct = isinstance(receiver, ast.Name) and receiver.id in imported
            constructed = isinstance(receiver, ast.Call) and isinstance(receiver.func, ast.Name) and receiver.func.id in imported
            if direct or constructed:
                violations.append(f"{path.relative_to(ROOT)}:{node.lineno}")
    assert not violations, "renamed/imported execution object executed outside the execution boundary: " + ", ".join(sorted(violations))


def test_http_application_never_constructs_or_calls_an_executor() -> None:
    tree = _tree(ROOT / "app.py")
    violations = []
    forbidden_imports = {"execution.real_gateway", "execution.adapter_gateway", "execution.icmarkets_mt5_demo_adapter", "execution.broker_registry"}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module in forbidden_imports:
            violations.append(f"app.py:{node.lineno}:import {node.module}")
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "execute":
            violations.append(f"app.py:{node.lineno}:execute")
    assert not violations, "HTTP application reaches an execution implementation directly: " + ", ".join(violations)


def test_ledger_mutations_are_only_called_by_execution_boundaries() -> None:
    allowed = {REAL_GATEWAY.resolve(), ROOT / "execution" / "gateway.py"}
    mutators = {"reserve", "record", "mark_accepted", "mark_rejected", "mark_unknown", "reconcile"}
    violations = []
    for path in _runtime_python_files():
        if path.resolve() in allowed:
            continue
        tree = _tree(path)
        ledger_names = {"ledger", "_ledger", "execution_ledger"}
        aliases = set(ledger_names)
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


def test_execution_ledger_file_is_not_written_through_a_side_channel() -> None:
    """The canonical ledger path may only be owned by the runtime composer/ledger implementation."""
    allowed = {ROOT / "core" / "operational_runtime.py", LEDGER}
    allowed = {path.resolve() for path in allowed}
    violations = []
    for path in _runtime_python_files():
        if path.resolve() in allowed:
            continue
        if "execution-ledger.json" in path.read_text(encoding="utf-8"):
            violations.append(str(path.relative_to(ROOT)))
    assert not violations, "canonical execution ledger path referenced outside its owner: " + ", ".join(sorted(violations))


def test_ledger_implementation_is_not_constructed_as_a_side_channel() -> None:
    allowed = {ROOT / "core" / "operational_runtime.py"}
    violations = []
    for path in _runtime_python_files():
        if path.resolve() == LEDGER.resolve() or path.resolve() in allowed:
            continue
        for node in ast.walk(_tree(path)):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "ExecutionLedger":
                violations.append(f"{path.relative_to(ROOT)}:{node.lineno}")
    assert not violations, "side-channel ExecutionLedger construction found: " + ", ".join(sorted(violations))


def test_execution_mode_environment_is_read_only_at_application_composition_boundary() -> None:
    violations = []
    allowed_files = {ROOT / "app.py", ROOT / "core" / "operational_runtime.py"}
    for path in _runtime_python_files():
        if path.resolve() in allowed_files:
            continue
        text = path.read_text(encoding="utf-8")
        if "CONTROLADOR_EXECUTION_PROVIDER" in text or "CONTROLADOR_EXECUTION_MODE" in text:
            violations.append(str(path.relative_to(ROOT)))
    assert not violations, "execution-mode environment is interpreted outside the composition boundary: " + ", ".join(sorted(violations))
