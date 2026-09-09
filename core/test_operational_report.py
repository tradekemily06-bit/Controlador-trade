from datetime import datetime, timezone

from core.models import Signal
from core.operation_memory import OperationMemory, OperationMemoryRecord
from core.operational_report import OperationalReport, OperationalReporter


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


def test_report_combines_snapshot_and_records():
    memory = OperationMemory()
    memory.append(make_record(1, "WIN"))
    memory.append(make_record(2, "LOSS"))

    report = OperationalReporter(memory).report()

    assert isinstance(report, OperationalReport)
    assert report.snapshot.total == 2
    assert report.snapshot.wins == 1
    assert report.snapshot.losses == 1
    assert len(report.records) == 2
    assert report.records[0].timestamp < report.records[1].timestamp


def test_report_respects_period_without_mutating_memory():
    memory = OperationMemory()
    memory.append(make_record(1, "WIN"))
    memory.append(make_record(2, "LOSS"))
    before = memory.records()

    report = OperationalReporter(memory).report(
        start=datetime(2026, 1, 1, 0, 2, tzinfo=timezone.utc),
        end=datetime(2026, 1, 1, 0, 2, tzinfo=timezone.utc),
    )

    assert report.snapshot.total == 1
    assert report.snapshot.losses == 1
    assert len(report.records) == 1
    assert memory.records() == before


def test_report_requires_memory():
    try:
        OperationalReporter(None)
    except ValueError as exc:
        assert "memory" in str(exc)
    else:
        raise AssertionError("expected ValueError")
