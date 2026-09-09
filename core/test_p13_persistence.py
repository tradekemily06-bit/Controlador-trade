from datetime import datetime, timezone

import pytest

from core.models import Signal
from core.operation_memory import OperationMemory, OperationMemoryRecord
from core.operation_memory_store import OperationMemoryStore
from core.operational_report import OperationalReporter
from core.report_export import OperationalReportExporter


def make_record(minute: int, result: str) -> OperationMemoryRecord:
    return OperationMemoryRecord(
        timestamp=datetime(2026, 1, 1, 0, minute, tzinfo=timezone.utc),
        signal=Signal.COMPRA,
        score=80.0,
        decision="EXECUTAR",
        reason="teste",
        result=result,
        symbol="TEST",
        timeframe="1m",
        quality_score=90.0,
        quality_level="FORTE",
        entry_conditions=("fechamento",),
    )


def test_memory_store_round_trip(tmp_path):
    memory = OperationMemory()
    memory.append(make_record(1, "WIN"))
    memory.append(make_record(2, "PENDENTE"))
    path = tmp_path / "memory.json"

    store = OperationMemoryStore(path)
    store.save(memory)
    restored = store.load()

    assert restored.records() == memory.records()


def test_memory_store_missing_file_is_empty(tmp_path):
    assert OperationMemoryStore(tmp_path / "missing.json").load().records() == ()


def test_memory_store_rejects_invalid_payload(tmp_path):
    path = tmp_path / "memory.json"
    path.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="lista"):
        OperationMemoryStore(path).load()


def test_report_export_is_deterministic(tmp_path):
    memory = OperationMemory()
    memory.append(make_record(1, "WIN"))
    report = OperationalReporter(memory).report()

    first = OperationalReportExporter.to_json(report)
    second = OperationalReportExporter.to_json(report)

    assert first == second
    assert '"records"' in first
    assert '"snapshot"' in first
    assert '"WIN"' in first

    path = tmp_path / "report.json"
    OperationalReportExporter.save_json(report, path)
    assert path.read_text(encoding="utf-8").rstrip() == first


def test_export_rejects_invalid_report():
    with pytest.raises(TypeError):
        OperationalReportExporter.to_json(None)
