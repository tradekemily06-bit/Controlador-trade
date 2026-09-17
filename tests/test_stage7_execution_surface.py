from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

# These are the production surfaces where low-level execution calls are
# intentionally allowed because they are themselves audited execution
# boundaries. Each exception must remain covered by dedicated tests and must
# not expose a public broker/adapter capability.
_ALLOWED = {
    Path("execution/adapter_gateway.py"),
    Path("execution/gateway.py"),
    Path("execution/real_gateway.py"),
    Path("execution/p125_sandbox_validation.py"),
    Path("execution/demo_broker_port.py"),
    Path("execution/demo_risk_dispatch_guard.py"),
}
_LOW_LEVEL_RECEIVER_HINTS = ("adapter", "broker", "executor")

# REAL authorization is a privileged capability. Production code must obtain
# it from the dedicated issuer rather than constructing the immutable contract
# directly. Tests are intentionally excluded so they can exercise the
# contract's defensive behavior.
_AUTHORIZATION_FACTORY = Path("core/real_authorization_issuer.py")


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
            if path.name.startswith("test_") or relative == _AUTHORIZATION_FACTORY:
                continue
            for line, constructor in _direct_real_authorization_constructors(path):
                unexpected.append(f"{relative}:{line}: {constructor}(...)")

    assert unexpected == [], (
        "Direct RealExecutionAuthorization construction detected outside the "
        "dedicated issuer. Treat this as a REAL-authorization side door:\n"
        + "\n".join(unexpected)
    )
