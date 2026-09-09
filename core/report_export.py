from __future__ import annotations

import json
from pathlib import Path

from core.operational_report import OperationalReport
from core.operation_memory_store import OperationMemoryStore


class OperationalReportExporter:
    """Exports validated operational reports to deterministic JSON."""

    @staticmethod
    def to_dict(report: OperationalReport) -> dict[str, object]:
        if not isinstance(report, OperationalReport):
            raise TypeError("report deve ser OperationalReport.")
        records = [OperationMemoryStore._serialize(record) for record in report.records]
        return {
            "generated_at": report.generated_at.isoformat(),
            "snapshot": {
                "total": report.snapshot.total,
                "completed": report.snapshot.completed,
                "pending": report.snapshot.pending,
                "wins": report.snapshot.wins,
                "losses": report.snapshot.losses,
                "ambiguous": report.snapshot.ambiguous,
                "win_rate": report.snapshot.win_rate,
                "loss_streak": report.snapshot.loss_streak,
                "max_loss_streak": report.snapshot.max_loss_streak,
                "direction": report.snapshot.direction,
                "quality": report.snapshot.quality,
                "decision_distribution": report.snapshot.decision_distribution,
            },
            "records": records,
        }

    @classmethod
    def to_json(cls, report: OperationalReport) -> str:
        return json.dumps(
            cls.to_dict(report),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )

    @classmethod
    def save_json(cls, report: OperationalReport, path: str | Path) -> None:
        if path is None:
            raise ValueError("path é obrigatório.")
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(cls.to_json(report) + "\n", encoding="utf-8")
