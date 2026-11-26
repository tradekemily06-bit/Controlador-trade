from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Iterable

from analysis.decision_record import DecisionRecord


def build_decision_report(records: Iterable[DecisionRecord], statistics: dict[str, Any]) -> dict[str, Any]:
    """Build a read-only report from the standalone decision-memory model.

    DecisionRecord is intentionally not coerced into OperationMemoryRecord:
    the two models have different semantics and outcome vocabularies.
    """
    items = list(records)
    if any(not isinstance(item, DecisionRecord) for item in items):
        raise TypeError("records must contain DecisionRecord instances")
    payload = {
        "report_type": "STANDALONE_DECISION_REPORT",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "record_count": len(items),
        "record_scope": "MOST_RECENT_LIMIT",
        "statistics_scope": "ALL_STORED_DECISIONS",
        "statistics": statistics,
        "records": [item.to_dict() for item in items],
        "execution_authorized": False,
        "source_model": "DecisionRecord",
        "legacy_operation_memory_conversion": False,
    }
    # Ensure the export is portable JSON before exposing it to callers.
    json.dumps(payload, ensure_ascii=False, allow_nan=False)
    return payload


def export_decision_report(report: dict[str, Any]) -> str:
    if not isinstance(report, dict) or report.get("report_type") != "STANDALONE_DECISION_REPORT":
        raise ValueError("invalid standalone decision report")
    return json.dumps(report, ensure_ascii=False, allow_nan=False, indent=2, sort_keys=True)
