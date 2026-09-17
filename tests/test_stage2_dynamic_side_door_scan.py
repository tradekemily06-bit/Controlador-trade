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
    """Dynamic lookup must not immediately invoke known raw execution surfaces."""
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
            if not isinstance(node.func, ast.Call):
                continue
            if not isinstance(node.func.func, ast.Name) or node.func.func.id != "getattr":
                continue
            if len(node.func.args) < 2:
                continue
            name = _literal_string(node.func.args[1])
            if name in forbidden:
                offenders.append(f"{relative}:{node.lineno}:{name}")

    assert not offenders, f"dynamic execution side door detected: {offenders}"


def test_dynamic_getattr_cannot_reach_raw_execution_surfaces_indirectly():
    """A dynamically resolved execution method must not be stored and invoked later."""
    forbidden = {"execute", "order_send"}
    offenders: list[str] = []

    class ScopeVisitor(ast.NodeVisitor):
        def __init__(self, relative: Path) -> None:
            self.relative = relative
            self.scopes: list[set[str]] = [set()]

        def _visit_scope(self, node: ast.AST) -> None:
            self.scopes.append(set())
            for child in ast.iter_child_nodes(node):
                self.visit(child)
            self.scopes.pop()

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            self._visit_scope(node)

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            self._visit_scope(node)

        def visit_Lambda(self, node: ast.Lambda) -> None:
            self._visit_scope(node)

        def visit_Assign(self, node: ast.Assign) -> None:
            if (
                isinstance(node.value, ast.Call)
                and isinstance(node.value.func, ast.Name)
                and node.value.func.id == "getattr"
                and len(node.value.args) >= 2
                and _literal_string(node.value.args[1]) in forbidden
            ):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        self.scopes[-1].add(target.id)
                        offenders.append(f"{self.relative}:{node.lineno}:{target.id}")
            self.generic_visit(node)

        def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
            if (
                isinstance(node.value, ast.Call)
                and isinstance(node.value.func, ast.Name)
                and node.value.func.id == "getattr"
                and len(node.value.args) >= 2
                and _literal_string(node.value.args[1]) in forbidden
            ):
                if isinstance(node.target, ast.Name):
                    self.scopes[-1].add(node.target.id)
                    offenders.append(f"{self.relative}:{node.lineno}:{node.target.id}")
            self.generic_visit(node)

        def visit_Call(self, node: ast.Call) -> None:
            if isinstance(node.func, ast.Name) and any(node.func.id in scope for scope in self.scopes):
                offenders.append(f"{self.relative}:{node.lineno}:{node.func.id}()")
            self.generic_visit(node)

    for path, tree in _parsed_production_files():
        relative = path.relative_to(ROOT)
        if relative in {Path("execution/adapter_gateway.py"), Path("execution/icmarkets_mt5_demo_adapter.py")}:
            continue
        ScopeVisitor(relative).visit(tree)

    assert not offenders, f"indirect dynamic execution side door detected: {offenders}"


def test_dynamic_attribute_helpers_cannot_reach_raw_execution_surfaces():
    """Common reflective helpers must not dynamically resolve raw execution methods."""
    forbidden = {"execute", "order_send"}
    offenders: list[str] = []

    for path, tree in _parsed_production_files():
        relative = path.relative_to(ROOT)
        if relative in {Path("execution/adapter_gateway.py"), Path("execution/icmarkets_mt5_demo_adapter.py")}:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                # operator.attrgetter("execute") / attrgetter("order_send")
                func = node.func
                if (
                    isinstance(func, ast.Attribute)
                    and func.attr == "attrgetter"
                    and node.args
                    and _literal_string(node.args[0]) in forbidden
                ):
                    offenders.append(f"{relative}:{node.lineno}:attrgetter:{_literal_string(node.args[0])}")

                # object.__getattribute__(obj, "execute") and equivalent direct reflective access.
                if (
                    isinstance(func, ast.Attribute)
                    and func.attr == "__getattribute__"
                    and len(node.args) >= 2
                    and _literal_string(node.args[1]) in forbidden
                ):
                    offenders.append(f"{relative}:{node.lineno}:__getattribute__:{_literal_string(node.args[1])}")

            if isinstance(node, ast.Subscript):
                key = node.slice
                name = _literal_string(key)
                if name in forbidden:
                    value = node.value
                    if isinstance(value, ast.Attribute) and value.attr == "__dict__":
                        offenders.append(f"{relative}:{node.lineno}:__dict__:{name}")
                    if isinstance(value, ast.Call) and isinstance(value.func, ast.Name) and value.func.id == "vars":
                        offenders.append(f"{relative}:{node.lineno}:vars:{name}")

    assert not offenders, f"reflective execution side door detected: {offenders}"


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
