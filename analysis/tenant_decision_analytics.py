"""Tenant-scoped statistics and reports derived only from owned decisions."""
from __future__ import annotations

from dataclasses import asdict
from typing import Iterable

from analysis.decision_record import DecisionRecord
from analysis.decision_report import build_decision_report, export_decision_report
from analysis.statistics import summarize, summarize_breakdowns, summarize_periods


def summarize_tenant_decisions(records: Iterable[DecisionRecord]) -> dict[str, object]:
    """Summarize exactly the supplied tenant-owned records; no global store reads."""
    items = list(records)
    if any(not isinstance(item, DecisionRecord) for item in items):
        raise TypeError("records must contain DecisionRecord instances")
    breakdowns = summarize_breakdowns(items)
    return {
        **asdict(summarize(items)),
        "periods": summarize_periods(items),
        "breakdowns": {
            **breakdowns,
            "by_symbol": breakdowns["symbols"],
            "by_timeframe": breakdowns["timeframes"],
            "by_signal": breakdowns["signals"],
            "by_score_band": breakdowns["score_bands"],
        },
        "scope": "TENANT_AND_SUBJECT",
        "source": "TENANT_SCOPED_DECISION_MEMORY",
        "records_considered": len(items),
        "win_rate_is_historical_outcome_ratio_not_prediction": True,
        "execution_authorized": False,
    }


def build_tenant_decision_report(
    records: Iterable[DecisionRecord], *, limit: int = 1000
) -> dict[str, object]:
    """Build an export from the owner's history, never from legacy global memory."""
    items = list(records)
    if any(not isinstance(item, DecisionRecord) for item in items):
        raise TypeError("records must contain DecisionRecord instances")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 1000:
        raise ValueError("limit deve ser um inteiro de 1 a 1000")
    statistics = summarize_tenant_decisions(items)
    report = build_decision_report(items[-limit:], statistics)
    report["scope"] = "TENANT_AND_SUBJECT"
    report["statistics_scope"] = "ALL_LOADED_TENANT_DECISIONS"
    report["statistics_records_considered"] = len(items)
    report["export_json"] = export_decision_report(report)
    return report
