from datetime import datetime, timezone

import pytest

from core.operation_lineage import OperationLineage, OperationLineageStore


def test_lineage_persists_full_identity_chain(tmp_path):
    store = OperationLineageStore(tmp_path / "lineage.json")
    created = OperationLineage(
        decision_id="decision-1",
        cycle_id="cycle-1",
        request_id="request-1",
        updated_at=datetime.now(timezone.utc),
    )
    store.put(created)

    stored = store.get("request-1")
    assert stored == created

    updated = store.attach_external_id(
        "request-1",
        "MT5-123",
        updated_at=datetime.now(timezone.utc),
    )
    assert updated.decision_id == "decision-1"
    assert updated.cycle_id == "cycle-1"
    assert updated.external_id == "MT5-123"
    assert store.get("request-1") == updated


def test_lineage_rejects_identity_rebinding(tmp_path):
    store = OperationLineageStore(tmp_path / "lineage.json")
    store.put(OperationLineage("decision-1", "cycle-1", "request-1"))

    with pytest.raises(ValueError, match="não pode mudar"):
        store.put(OperationLineage("decision-2", "cycle-1", "request-1"))

    store.attach_external_id("request-1", "MT5-123")
    with pytest.raises(ValueError, match="conflitante"):
        store.attach_external_id("request-1", "MT5-999")
