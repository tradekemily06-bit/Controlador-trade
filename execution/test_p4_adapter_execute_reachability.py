from __future__ import annotations

import ast
from pathlib import Path


def test_adapter_execute_has_single_production_call_site():
    """Broker adapters may only be invoked by the sanctioned adapter gateway.

    The test deliberately checks source syntax rather than runtime behavior:
    a new integration must not accidentally create a second path to
    adapter.execute(...) that bypasses the REAL/DEMO boundary.
    """

    root = Path(__file__).resolve().parents[1]
    violations: list[str] = []
    sanctioned_sites: list[str] = []

    for path in root.rglob("*.py"):
        relative = path.relative_to(root)
        if path.name.startswith("test_"):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not isinstance(node.func, ast.Attribute) or node.func.attr != "execute":
                continue

            receiver = node.func.value
            receiver_name = None
            chained_registry_get = (
                isinstance(receiver, ast.Call)
                and isinstance(receiver.func, ast.Attribute)
                and receiver.func.attr == "get"
            )
            if isinstance(receiver, ast.Name):
                receiver_name = receiver.id
            elif isinstance(receiver, ast.Attribute):
                receiver_name = receiver.attr

            if (
                (receiver_name and "adapter" in receiver_name.lower())
                or chained_registry_get
            ):
                site = f"{relative}:{node.lineno}"
                violations.append(site)
                if relative.as_posix() == "execution/adapter_gateway.py":
                    sanctioned_sites.append(site)

    assert violations == sanctioned_sites
    assert len(sanctioned_sites) == 1
