from datetime import datetime, timedelta

import pytest

from core.discovery_memory import (
    DiscoveryMemory,
    DiscoveryMemoryRecord,
    DiscoveryMemoryValidationError,
)


def record(offset: int = 0, **kwargs) -> DiscoveryMemoryRecord:
    return DiscoveryMemoryRecord(
        timestamp=datetime(2026, 1, 1) + timedelta(minutes=offset),
        relationships=("RANGE_DIRECTION=UP",),
        evidence=("observed on completed candles",),
        **kwargs,
    )


def test_discovery_memory_stores_evidence_without_execution_authority():
    memory = DiscoveryMemory()
    memory.append(record(validation_status="VALIDATED", operationally_admitted=True))

    stored = memory.records()[0]
    assert stored.operationally_admitted is True
    assert stored.execution_authorized is False
    assert memory.summary() == {
        "total": 1,
        "admitted": 1,
        "execution_authorized": 0,
    }


def test_discovery_memory_rejects_execution_authorization():
    with pytest.raises(DiscoveryMemoryValidationError):
        record(execution_authorized=True)


def test_discovery_memory_requires_chronological_records():
    memory = DiscoveryMemory()
    memory.append(record(offset=10))

    with pytest.raises(DiscoveryMemoryValidationError):
        memory.append(record(offset=5))
