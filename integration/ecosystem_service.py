from __future__ import annotations

from dataclasses import asdict
from typing import Any, Iterable

from analysis.decision_record import DecisionRecord
from analysis.statistics import summarize
from core.signal_engine import SignalEngine


class EcosystemService:
    """Application-level orchestration without broker execution."""

    def __init__(self, engine: SignalEngine | None = None) -> None:
        self.engine = engine or SignalEngine()
        self.memory: list[DecisionRecord] = []

    def analyze(self, payload: dict[str, Any]) -> DecisionRecord:
        result = self.engine.evaluate(
            score=payload.get("score", 50),
            confirmed=payload.get("confirmed", False),
            filters_ok=payload.get("filters_ok", True),
            symbol=payload.get("symbol"),
            timeframe=payload.get("timeframe"),
        )
        record = DecisionRecord.from_analysis(result)
        self.memory.append(record)
        return record

    def replay(self, cases: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for index, payload in enumerate(cases, start=1):
            record = self.analyze(payload)
            results.append({"step": index, **record.to_dict()})
        return results

    def statistics(self) -> dict[str, Any]:
        return asdict(summarize(self.memory))

    def memory_view(self, limit: int = 50) -> list[dict[str, Any]]:
        if limit < 1:
            raise ValueError("limit deve ser maior que zero")
        return [item.to_dict() for item in self.memory[-limit:]][::-1]

    def system_status(self) -> dict[str, Any]:
        return {
            "mode": "SIMULACAO",
            "execution_allowed": False,
            "decision_engine": "ONLINE",
            "memory": "ONLINE",
            "replay": "ONLINE",
            "statistics": "ONLINE",
            "risk_gate": "ONLINE",
            "news": "AGUARDANDO_FONTE",
            "mt5_demo": "VALIDACAO_OPERACIONAL_PENDENTE",
            "real": "DESABILITADO",
        }
