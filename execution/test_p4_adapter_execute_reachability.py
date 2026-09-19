from __future__ import annotations

import ast
from pathlib import Path


def test_adapter_execute_has_single_production_call_site():
    """Broker adapters may only be invoked by the sanctioned adapter gateway."""
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


def test_real_adapter_gateway_capability_cannot_gain_a_second_call_site():
    """REAL dispatch must remain a single, capability-gated source of truth."""
    root = Path(__file__).resolve().parents[1]
    call_sites: list[str] = []
    invalid_capability_calls: list[str] = []

    for path in root.rglob("*.py"):
        relative = path.relative_to(root)
        if path.name.startswith("test_"):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not isinstance(node.func, ast.Attribute) or node.func.attr != "execute_real":
                continue

            site = f"{relative}:{node.lineno}"
            call_sites.append(site)

            if relative.as_posix() != "execution/real_gateway.py":
                invalid_capability_calls.append(site)
                continue

            capability_kw = next(
                (kw for kw in node.keywords if kw.arg == "capability"),
                None,
            )
            if capability_kw is None:
                invalid_capability_calls.append(site)

    assert invalid_capability_calls == []
    assert len(call_sites) == 1
    assert call_sites[0].startswith("execution/real_gateway.py:")
