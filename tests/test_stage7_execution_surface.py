from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

# These are the only production surfaces where a low-level execution call is
# intentionally allowed. Tests and sandbox simulators are excluded from this
# structural guard because they exercise adapters directly by design.
_ALLOWED = {
    Path("execution/adapter_gateway.py"),
    Path("execution/gateway.py"),
    Path("execution/real_gateway.py"),
    Path("execution/p125_sandbox_validation.py"),
}
_LOW_LEVEL_RECEIVER_HINTS = ("adapter", "broker", "executor")


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
