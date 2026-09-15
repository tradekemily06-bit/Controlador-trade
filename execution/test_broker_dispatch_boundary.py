from __future__ import annotations

import ast
from pathlib import Path


ALLOWED_DISPATCH_MODULES = {"icmarkets_mt5_demo_adapter.py"}


def _has_order_send_call(text: str) -> bool:
    """Detect an actual ``order_send(...)`` call, not a docstring/comment mention."""
    tree = ast.parse(text)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        function = node.func
        if isinstance(function, ast.Attribute) and function.attr == "order_send":
            return True
        if isinstance(function, ast.Name) and function.id == "order_send":
            return True
    return False


def test_mt5_order_send_exists_only_inside_broker_adapter_boundary() -> None:
    """Prevent a future script/helper from creating a second broker dispatch path."""
    execution_dir = Path(__file__).resolve().parent
    violations: list[str] = []

    for path in execution_dir.glob("*.py"):
        if path.name.startswith("test_") or path.name in ALLOWED_DISPATCH_MODULES:
            continue
        text = path.read_text(encoding="utf-8")
        if _has_order_send_call(text):
            violations.append(path.name)

    assert not violations, (
        "dispatch broker direto fora do adapter autorizado: "
        + ", ".join(sorted(violations))
    )
