from pathlib import Path


CRITICAL_DURABLE_MODULES = (
    Path("core/durable_json.py"),
    Path("core/runtime_checkpoint.py"),
    Path("core/operation_memory_store.py"),
    Path("core/operational_safety_store.py"),
    Path("execution/execution_ledger.py"),
    Path("execution/execution_lifecycle.py"),
)


def test_critical_durable_modules_do_not_reintroduce_check_then_use_json_reads():
    """Durable reads must remain exception-driven/atomic, not TOCTOU-prone."""
    violations: list[str] = []
    for relative in CRITICAL_DURABLE_MODULES:
        source = relative.read_text(encoding="utf-8")
        for token in (".exists()", ".is_symlink()", ".read_text(", "json.loads("):
            if token in source:
                violations.append(f"{relative}:{token}")
    assert violations == []
