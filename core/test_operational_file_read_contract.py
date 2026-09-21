from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_operational_stores_use_descriptor_based_reads():
    paths = (
        "core/runtime_checkpoint.py",
        "core/operation_memory_store.py",
        "core/operational_safety_store.py",
        "execution/execution_lifecycle.py",
        "execution/execution_ledger.py",
    )
    for relative in paths:
        source = (ROOT / relative).read_text(encoding="utf-8")
        assert "read_regular_utf8(" in source, relative
        assert "self.path.read_text(" not in source, relative
