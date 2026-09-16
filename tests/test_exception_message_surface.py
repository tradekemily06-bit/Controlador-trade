from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
# These are user-facing / broker-facing runtime modules where exception details
# must never become an API or execution-boundary message.
TARGETS = (
    ROOT / "app.py",
    ROOT / "execution",
    ROOT / "security",
)


def _python_files() -> list[Path]:
    files: list[Path] = []
    for target in TARGETS:
        if target.is_file():
            files.append(target)
        elif target.is_dir():
            files.extend(target.rglob("*.py"))
    return files


def _is_str_exc(node: ast.Call) -> bool:
    return (
        isinstance(node.func, ast.Name)
        and node.func.id == "str"
        and len(node.args) == 1
        and isinstance(node.args[0], ast.Name)
        and node.args[0].id in {"exc", "error", "exception"}
    )


def test_runtime_boundaries_do_not_format_raw_exception_details() -> None:
    violations: list[str] = []
    for path in _python_files():
        # Test modules are intentionally excluded; this scan protects runtime
        # code, not assertions that inspect exception text.
        if path.name.startswith("test_") or path.parent.name == "tests":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and _is_str_exc(node):
                violations.append(f"{path.relative_to(ROOT)}:{node.lineno}")
    assert not violations, "raw exception details found at runtime boundary: " + ", ".join(violations)
