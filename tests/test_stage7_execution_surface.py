from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

_ALLOWED = {
    Path("execution/adapter_gateway.py"),
    Path("execution/gateway.py"),
    Path("execution/real_gateway.py"),
    Path("execution/p125_sandbox_validation.py"),
    Path("execution/demo_broker_port.py"),
    Path("execution/demo_risk_dispatch_guard.py"),
}
_LOW_LEVEL_RECEIVER_HINTS = ("adapter", "broker", "executor")

# REAL authorization is a privileged capability. The immutable contract module
# contains the low-level constructor used by its dedicated issuer helper; that
# constructor is not itself a public production issuance path. All consumers
# must still obtain active authority through core/real_authorization_issuer.py.
_AUTHORIZATION_FACTORY = Path("core/real_authorization_issuer.py")
_AUTHORIZATION_CONTRACT = Path("core/p112_real_execution_contract.py")


def _direct_execute_calls(path: Path) -> list[tuple[int, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    hits: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Attribute) or node.func.attr != "execute":
            continue
        receiver = ast.unparse(node.func.value)
        terminal = receiver.rsplit(".", 1)[-1].lower()
        if any(hint in terminal for hint in _LOW_LEVEL_RECEIVER_HINTS):
            hits.append((node.lineno, receiver))
    return hits


def _direct_real_authorization_constructors(path: Path) -> list[tuple[int, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    hits: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id == "RealExecutionAuthorization":
            hits.append((node.lineno, ast.unparse(func)))
        elif isinstance(func, ast.Attribute) and func.attr == "RealExecutionAuthorization":
            hits.append((node.lineno, ast.unparse(func)))
    return hits


def _real_authorization_factory_calls(path: Path) -> list[tuple[int, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    hits: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id == "_issue_real_authorization":
            hits.append((node.lineno, ast.unparse(func)))
        elif isinstance(func, ast.Attribute) and func.attr == "_issue_real_authorization":
            hits.append((node.lineno, ast.unparse(func)))
    return hits


def _real_authorization_factory_imports(path: Path) -> list[tuple[int, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    hits: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "core.p112_real_execution_contract":
            for alias in node.names:
                if alias.name == "_issue_real_authorization":
                    hits.append((node.lineno, alias.name))
    return hits


def test_production_low_level_execution_calls_stay_on_known_boundaries():
    unexpected: list[str] = []
    for path in sorted((ROOT / "execution").rglob("*.py")):
        relative = path.relative_to(ROOT)
        if relative in _ALLOWED or path.name.startswith("test_"):
            continue
        for line, receiver in _direct_execute_calls(path):
            unexpected.append(f"{relative}:{line}: {receiver}.execute(...)")

    assert unexpected == [], (
        "New low-level adapter/broker/executor call detected outside the audited "
        "execution boundaries. Review it as a potential side door before allowing it:\n"
        + "\n".join(unexpected)
    )


def test_production_real_authorization_is_issued_by_the_dedicated_factory():
    unexpected: list[str] = []
    for root in (ROOT / "core", ROOT / "execution"):
        for path in sorted(root.rglob("*.py")):
            relative = path.relative_to(ROOT)
            if (
                path.name.startswith("test_")
                or relative in {_AUTHORIZATION_FACTORY, _AUTHORIZATION_CONTRACT}
            ):
                continue
            for line, constructor in _direct_real_authorization_constructors(path):
                unexpected.append(f"{relative}:{line}: {constructor}(...)")

    assert unexpected == [], (
        "Direct RealExecutionAuthorization construction detected outside the "
        "dedicated issuer. Treat this as a REAL-authorization side door:\n"
        + "\n".join(unexpected)
    )


def test_production_real_authorization_factory_has_only_one_consumer():
    unexpected_calls: list[str] = []
    unexpected_imports: list[str] = []
    for root in (ROOT / "core", ROOT / "execution"):
        for path in sorted(root.rglob("*.py")):
            relative = path.relative_to(ROOT)
            if path.name.startswith("test_") or relative in {_AUTHORIZATION_FACTORY, _AUTHORIZATION_CONTRACT}:
                continue
            for line, factory in _real_authorization_factory_calls(path):
                unexpected_calls.append(f"{relative}:{line}: {factory}(...)")
            for line, imported in _real_authorization_factory_imports(path):
                unexpected_imports.append(f"{relative}:{line}: {imported}")

    assert unexpected_calls == [] and unexpected_imports == [], (
        "The low-level REAL authorization factory must remain reachable only "
        "from core/real_authorization_issuer.py. Any new consumer is a potential "
        "authority side door:\n"
        + "\n".join(unexpected_calls + unexpected_imports)
    )
