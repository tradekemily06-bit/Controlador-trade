from __future__ import annotations

import pytest

from integration.ecosystem_service import EcosystemService


def test_analyze_attaches_trusted_owner() -> None:
    service = EcosystemService()
    record = service.analyze({"score": 90, "confirmed": True, "filters_ok": True}, subject_id="user-a", tenant_id="tenant-a")
    assert record.subject_id == "user-a"
    assert record.tenant_id == "tenant-a"


def test_replay_attaches_one_trusted_owner_to_every_record() -> None:
    service = EcosystemService()
    results = service.replay(
        [{"score": 90, "confirmed": True, "filters_ok": True} for _ in range(3)],
        subject_id="user-a",
        tenant_id="tenant-a",
    )
    assert len(results) == 3
    assert {(item["subject_id"], item["tenant_id"]) for item in results} == {("user-a", "tenant-a")}


def test_partial_owner_context_fails_closed() -> None:
    service = EcosystemService()
    with pytest.raises(PermissionError):
        service.analyze({"score": 90}, subject_id="user-a")
    with pytest.raises(PermissionError):
        service.replay([{"score": 90}], tenant_id="tenant-a")
    with pytest.raises(PermissionError):
        service.record_outcome("missing", "WIN", subject_id="user-a")


def test_outcome_requires_matching_subject_and_tenant() -> None:
    service = EcosystemService()
    record = service.analyze({"score": 90, "confirmed": True, "filters_ok": True}, subject_id="user-a", tenant_id="tenant-a")

    updated = service.record_outcome(record.decision_id, "WIN", subject_id="user-a", tenant_id="tenant-a")
    assert updated.outcome == "WIN"

    with pytest.raises(PermissionError):
        service.record_outcome(record.decision_id, "LOSS", subject_id="user-b", tenant_id="tenant-a")
    with pytest.raises(PermissionError):
        service.record_outcome(record.decision_id, "LOSS", subject_id="user-a", tenant_id="tenant-b")
