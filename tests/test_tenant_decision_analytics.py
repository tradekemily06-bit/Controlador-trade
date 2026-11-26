from __future__ import annotations

import json

import pytest

from analysis.decision_record import DecisionRecord
from analysis.tenant_decision_analytics import (
    build_tenant_decision_report,
    summarize_tenant_decisions,
)


def _record(decision_id: str, outcome: str | None, signal: str = "COMPRA") -> DecisionRecord:
    return DecisionRecord(
        decision_id=decision_id,
        created_at="2026-11-26T12:00:00+00:00",
        symbol="EURUSD",
        timeframe="M5",
        signal=signal,
        score=82.0,
        confirmed=True,
        reason="manual study",
        outcome=outcome,
    )


def test_tenant_statistics_count_only_manual_closed_outcomes():
    result = summarize_tenant_decisions([
        _record("win", "WIN"),
        _record("loss", "LOSS", signal="VENDA"),
        _record("open", "OPEN"),
        _record("unreviewed", None),
    ])

    assert result["total"] == 4
    assert result["wins"] == 1
    assert result["losses"] == 1
    assert result["open"] == 1
    assert result["closed"] == 2
    assert result["win_rate"] == 50.0
    assert result["win_rate_status"] == "AVAILABLE"
    assert result["scope"] == "TENANT_AND_SUBJECT"
    assert result["win_rate_is_historical_outcome_ratio_not_prediction"] is True
    assert result["execution_authorized"] is False


def test_tenant_report_limits_displayed_records_but_keeps_full_owner_statistics():
    records = [
        _record("win", "WIN"),
        _record("loss", "LOSS", signal="VENDA"),
    ]
    report = build_tenant_decision_report(records, limit=1)

    assert report["record_count"] == 1
    assert report["records"][0]["decision_id"] == "loss"
    assert report["statistics_records_considered"] == 2
    assert report["statistics"]["total"] == 2
    assert report["statistics"]["win_rate"] == 50.0
    assert report["statistics_scope"] == "ALL_LOADED_TENANT_DECISIONS"
    assert report["execution_authorized"] is False
    exported = json.loads(report["export_json"])
    assert exported["scope"] == "TENANT_AND_SUBJECT"


@pytest.mark.parametrize("limit", [0, 1001, True, 1.5, "10"])
def test_tenant_report_rejects_invalid_record_limit(limit):
    with pytest.raises(ValueError, match="limit"):
        build_tenant_decision_report([], limit=limit)


def test_tenant_analytics_rejects_non_decision_objects():
    with pytest.raises(TypeError, match="DecisionRecord"):
        summarize_tenant_decisions([{"signal": "COMPRA"}])
