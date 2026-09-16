from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXECUTION = ROOT / "execution"


def _production_python_files() -> list[Path]:
    return [
        path for path in EXECUTION.glob("*.py")
        if path.is_file() and not path.name.startswith("test_")
    ]


def test_no_production_factory_constructs_real_gateway_outside_gateway_module():
    offenders: list[str] = []
    for path in _production_python_files():
        if path.name == "real_gateway.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "RealExecutionGateway":
                offenders.append(str(path.relative_to(ROOT)))
    assert not offenders, f"REAL gateway constructed outside authoritative composition boundary: {offenders}"


def test_registry_adapter_lookup_side_door_is_confined_to_adapter_gateway():
    offenders: list[str] = []
    for path in _production_python_files():
        if path.name == "adapter_gateway.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "_get_for_gateway":
                offenders.append(str(path.relative_to(ROOT)))
    assert not offenders, f"registry adapter lookup side door detected: {offenders}"


def test_raw_adapter_execute_is_confined_to_adapter_gateway():
    offenders: list[str] = []
    for path in _production_python_files():
        if path.name == "adapter_gateway.py":
            continue
        if "adapter.execute(" in path.read_text(encoding="utf-8"):
            offenders.append(str(path.relative_to(ROOT)))
    assert not offenders, f"raw adapter.execute side door detected: {offenders}"


def test_mt5_demo_adapter_construction_is_confined_to_demo_broker_port():
    offenders: list[str] = []
    for path in _production_python_files():
        if path.name == "demo_broker_port.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "ICMarketsMT5DemoAdapter":
                offenders.append(str(path.relative_to(ROOT)))
    assert not offenders, f"raw MT5 DEMO adapter construction side door detected: {offenders}"


def test_registry_does_not_expose_adapter_objects_through_legacy_getters():
    source = (EXECUTION / "broker_registry.py").read_text(encoding="utf-8")
    assert "def get(" not in source
    assert "def get_adapter(" not in source
    assert "return self._adapters" not in source
