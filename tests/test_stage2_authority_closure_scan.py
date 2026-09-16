from __future__ import annotations

import ast
from pathlib import Path

import pytest

from integration.execution_provider import (
    ExecutionProviderConfigurationError,
    build_demo_execution_port,
)


ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_DIRS = (ROOT / "core", ROOT / "execution", ROOT / "integration", ROOT / "security")


def _production_files() -> list[Path]:
    files: list[Path] = []
    for directory in PRODUCTION_DIRS:
        if not directory.exists():
            continue
        files.extend(
            path for path in directory.glob("*.py")
            if path.is_file() and not path.name.startswith("test_")
        )
    return files


def test_no_production_real_authority_uses_unsafe_serialization_hooks():
    offenders: list[str] = []
    forbidden_imports = {"pickle", "marshal", "shelve", "copyreg"}
    forbidden_methods = {"__setstate__", "__reduce__", "__reduce_ex__"}

    for path in _production_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                if any(alias.name.split(".", 1)[0] in forbidden_imports for alias in node.names):
                    offenders.append(str(path.relative_to(ROOT)))
            elif isinstance(node, ast.ImportFrom):
                if node.module and node.module.split(".", 1)[0] in forbidden_imports:
                    offenders.append(str(path.relative_to(ROOT)))
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in forbidden_methods:
                offenders.append(str(path.relative_to(ROOT)))

    assert not offenders, f"unsafe serialization/reconstruction hook detected in production: {sorted(set(offenders))}"


def test_raw_broker_order_send_call_is_ast_confined_to_mt5_adapter():
    offenders: list[str] = []
    allowed = "icmarkets_mt5_demo_adapter.py"
    for path in _production_files():
        if path.name == allowed:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "order_send":
                offenders.append(str(path.relative_to(ROOT)))

    assert not offenders, f"raw broker order_send side door detected: {offenders}"


@pytest.mark.parametrize("provider", ["real", "REAL", "live", "LIVE", "production", "PRODUCTION"])
def test_demo_configuration_cannot_select_a_real_or_live_provider(provider: str):
    with pytest.raises(ExecutionProviderConfigurationError):
        build_demo_execution_port(provider)


def test_demo_configuration_exposes_only_demo_ports():
    paper = build_demo_execution_port("paper")
    assert type(paper).__name__ == "PaperExecutor"
    assert not hasattr(paper, "order_send")

    mt5_demo = build_demo_execution_port("ic_markets_mt5_demo")
    assert type(mt5_demo).__name__ == "DemoBrokerExecutionPort"
    assert not hasattr(mt5_demo, "order_send")
    assert not type(mt5_demo).__name__.endswith("Adapter")
