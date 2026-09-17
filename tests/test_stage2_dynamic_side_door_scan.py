from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXCLUDED = {".git", ".venv", "venv", "__pycache__"}


def _production_python_files() -> list[Path]:
    return sorted(
        path
        for path in ROOT.rglob("*.py")
        if path.is_file()
        and not any(part in EXCLUDED for part in path.parts)
        and not path.name.startswith("test_")
    )


def _parsed_production_files() -> list[tuple[Path, ast.AST]]:
    return [
        (path, ast.parse(path.read_text(encoding="utf-8"), filename=str(path)))
        for path in _production_python_files()
    ]


def _literal_string(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def test_dynamic_getattr_cannot_reach_raw_execution_surfaces():
    """Dynamic attribute lookup must not reopen known execution side doors."""
    forbidden = {"execute", "order_send"}
    offenders: list[str] = []

    for path, tree in _parsed_production_files():
        relative = path.relative_to(ROOT)
        allowed = {
            Path("execution/adapter_gateway.py"),
            Path("execution/icmarkets_mt5_demo_adapter.py"),
        }
        if relative in allowed:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not isinstance(node.func, ast.Name) or node.func.id != "getattr":
                continue
            if len(node.args) < 2:
                continue
            name = _literal_string(node.args[1])
            if name in forbidden:
                offenders.append(f"{relative}:{node.lineno}:{name}")

    assert not offenders, f"dynamic execution side door detected: {offenders}"


def test_dynamic_getattr_cannot_reach_private_real_capabilities():
    """Private capability objects must not be recoverable through dynamic lookup."""
    forbidden = {
        "_BROKER_GATEWAY_CAPABILITY",
        "_REAL_ADAPTER_GATEWAY_CAPABILITY",
        "_DEMO_ADAPTER_CAPABILITY",
        "_REAL_AUTHORIZATION_ISSUER_CAPABILITY",
        "_REAL_ADMISSION_ISSUER_CAPABILITY",
    }
    offenders: list[str] = []

    for path, tree in _parsed_production_files():
        relative = path.relative_to(ROOT)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not isinstance(node.func, ast.Name) or node.func.id != "getattr":
                continue
            if len(node.args) < 2:
                continue
            name = _literal_string(node.args[1])
            if name in forbidden:
                offenders.append(f"{relative}:{node.lineno}:{name}")

    assert not offenders, f"dynamic private capability lookup detected: {offenders}"
