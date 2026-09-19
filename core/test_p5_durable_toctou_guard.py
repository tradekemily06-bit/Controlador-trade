import ast
from pathlib import Path


CRITICAL_DURABLE_MODULES = (
    Path("core/durable_json.py"),
    Path("core/runtime_checkpoint.py"),
    Path("core/operation_memory_store.py"),
    Path("core/operational_safety_store.py"),
    Path("execution/execution_ledger.py"),
    Path("execution/execution_lifecycle.py"),
)

FORBIDDEN_PATH_CALLS = {".exists", ".is_symlink", ".read_text"}


def test_critical_durable_modules_do_not_reintroduce_check_then_use_json_reads():
    """Durable modules must not reintroduce filesystem check-then-use calls."""
    violations: list[str] = []
    for relative in CRITICAL_DURABLE_MODULES:
        source = relative.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(relative))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                token = f".{node.func.attr}"
                if token in FORBIDDEN_PATH_CALLS:
                    violations.append(f"{relative}:{token}:{node.lineno}")
    assert violations == []
