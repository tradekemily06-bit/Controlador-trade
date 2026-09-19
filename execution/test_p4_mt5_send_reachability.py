from __future__ import annotations

import ast
from pathlib import Path


def test_mt5_order_send_has_single_production_boundary():
    """No production module may submit directly to MT5 outside the sanctioned adapter.

    A direct order_send bypasses the broker gateway, ledger, lifecycle and REAL/DEMO
    controls. The only production owner of this irreversible MT5 primitive is the
    IC Markets MT5 adapter itself.
    """
    root = Path(__file__).resolve().parents[1]
    allowed = Path("execution/icmarkets_mt5_demo_adapter.py")
    violations: list[str] = []

    for path in root.rglob("*.py"):
        relative = path.relative_to(root)
        if path.name.startswith("test_") or relative == allowed:
            continue

        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr != "order_send":
                continue
            violations.append(f"{relative}:{node.lineno}")

    assert violations == []
