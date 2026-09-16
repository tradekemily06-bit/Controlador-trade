from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXECUTION = ROOT / "execution"
CORE = ROOT / "core"


def _production_python_files() -> list[Path]:
    return [
        path for path in EXECUTION.glob("*.py")
        if path.is_file() and not path.name.startswith("test_")
    ]


def _core_production_python_files() -> list[Path]:
    return [
        path for path in CORE.glob("*.py")
        if path.is_file() and not path.name.startswith("test_")
    ]


def _imports_private_name(tree: ast.AST, private_name: str) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if any(alias.name == private_name for alias in node.names):
                return True
        elif isinstance(node, ast.Import):
            if any(alias.name.rsplit(".", 1)[-1] == private_name for alias in node.names):
                return True
    return False


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


def test_registry_private_adapter_storage_is_not_read_outside_registry():
    offenders: list[str] = []
    for path in _production_python_files():
        if path.name == "broker_registry.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in {"_adapters", "_adapter_ids"}:
                offenders.append(str(path.relative_to(ROOT)))
    assert not offenders, f"raw registry storage access side door detected: {offenders}"


def test_broker_gateway_capability_import_is_confined_to_adapter_gateway():
    offenders: list[str] = []
    for path in _production_python_files():
        if path.name == "adapter_gateway.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        if _imports_private_name(tree, "_BROKER_GATEWAY_CAPABILITY"):
            offenders.append(str(path.relative_to(ROOT)))
    assert not offenders, f"broker gateway capability leaked outside adapter gateway: {offenders}"


def test_real_authorization_capability_import_is_confined_to_issuer():
    offenders: list[str] = []
    for path in _core_production_python_files():
        if path.name in {"real_privilege_issuer.py", "p112_real_execution_contract.py"}:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        if _imports_private_name(tree, "_REAL_AUTHORIZATION_ISSUER_CAPABILITY"):
            offenders.append(str(path.relative_to(ROOT)))
    assert not offenders, f"REAL authorization issuer capability leaked outside authority: {offenders}"


def test_real_admission_capability_import_is_confined_to_issuer():
    offenders: list[str] = []
    for path in _core_production_python_files():
        if path.name in {"real_privilege_issuer.py", "p117_real_admission.py"}:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        if _imports_private_name(tree, "_REAL_ADMISSION_ISSUER_CAPABILITY"):
            offenders.append(str(path.relative_to(ROOT)))
    assert not offenders, f"REAL admission issuer capability leaked outside authority: {offenders}"


def test_no_production_module_constructs_active_real_authorization_directly():
    offenders: list[str] = []
    for path in [*_production_python_files(), *_core_production_python_files()]:
        if path.name == "p112_real_execution_contract.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "RealExecutionAuthorization":
                offenders.append(str(path.relative_to(ROOT)))
    assert not offenders, f"direct REAL authorization construction side door detected: {offenders}"
