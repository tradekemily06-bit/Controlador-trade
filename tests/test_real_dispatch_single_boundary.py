from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ALLOWED_ORDER_SEND = ROOT / "execution" / "icmarkets_mt5_demo_adapter.py"


def _runtime_python_files() -> list[Path]:
    files: list[Path] = []
    for directory in (ROOT / "execution", ROOT / "integration", ROOT / "core", ROOT / "security"):
        files.extend(path for path in directory.rglob("*.py") if not path.name.startswith("test_"))
    files.append(ROOT / "app.py")
    return files


def test_order_send_exists_only_inside_the_broker_adapter() -> None:
    violations: list[str] = []
    for path in _runtime_python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not isinstance(node.func, ast.Attribute) or node.func.attr != "order_send":
                continue
            if path.resolve() != ALLOWED_ORDER_SEND.resolve():
                violations.append(str(path.relative_to(ROOT)))
    assert not violations, "direct broker order_send bypass found outside the official adapter: " + ", ".join(sorted(violations))


def test_real_gateway_construction_is_not_replicated_outside_execution_boundary() -> None:
    violations: list[str] = []
    for path in _runtime_python_files():
        if path == ROOT / "execution" / "real_gateway.py":
            continue
        text = path.read_text(encoding="utf-8")
        if "RealExecutionGateway(" in text:
            violations.append(str(path.relative_to(ROOT)))
    assert not violations, "REAL gateway construction bypass found outside execution/real_gateway.py: " + ", ".join(sorted(violations))
