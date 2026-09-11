from __future__ import annotations

from dataclasses import asdict
from typing import Any, Iterable

from analysis.decision_record import DecisionRecord
from analysis.statistics import summarize
from core.risk_manager import RiskManager
from core.signal_engine import SignalEngine
from integration.news_provider import UnconfiguredNewsProvider


class EcosystemService:
    """Application orchestration; broker execution remains outside this layer."""

    def __init__(self, engine: SignalEngine | None = None) -> None:
        self.engine = engine or SignalEngine()
        self.memory: list[DecisionRecord] = []
        self.risk = RiskManager()
        self.news = UnconfiguredNewsProvider()

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
            if not isinstance(payload, dict):
                raise ValueError("cada cenário deve ser um objeto")
            record = self.analyze(payload)
            results.append({"step": index, **record.to_dict()})
        return results

    def record_outcome(self, decision_id: str, outcome: str) -> DecisionRecord:
        for index, record in enumerate(self.memory):
            if record.decision_id == decision_id:
                updated = record.with_outcome(outcome)
                self.memory[index] = updated
                return updated
        raise ValueError("decision_id não encontrado")

    def statistics(self) -> dict[str, Any]:
        return asdict(summarize(self.memory))

    def memory_view(self, limit: int = 50) -> list[dict[str, Any]]:
        if limit < 1:
            raise ValueError("limit deve ser maior que zero")
        return [item.to_dict() for item in self.memory[-limit:]][::-1]

    def risk_status(self) -> dict[str, Any]:
        decision = self.risk.evaluate()
        return {
            "allowed": decision.allowed,
            "reason": decision.reason,
            "configured_limits": {
                "daily_loss_limit": self.risk.daily_loss_limit,
                "max_operations": self.risk.max_operations,
                "max_consecutive_losses": self.risk.max_consecutive_losses,
            },
            "news_provider": "UNCONFIGURED",
        }

    def news_status(self, limit: int = 10) -> dict[str, Any]:
        return {"provider": "UNCONFIGURED", "live": False, "items": [asdict(item) for item in self.news.latest(limit=limit)]}

    def connections(self) -> dict[str, Any]:
        return {
            "decision_core": "ONLINE",
            "execution_gateway": "ONLINE",
            "ic_markets_mt5_demo": "DEMO_VALIDADO",
            "cTrader": "FUTURO_NAO_BLOQUEANTE",
            "real": "DESABILITADO",
        }

    def system_status(self) -> dict[str, Any]:
        return {
            "mode": "SIMULACAO",
            "execution_allowed": False,
            "execution": "bloqueada_por_padrao",
            "decision_engine": "ONLINE",
            "memory": "ONLINE",
            "replay": "ONLINE",
            "statistics": "ONLINE",
            "risk_gate": "ONLINE",
            "news": "AGUARDANDO_FONTE",
            "mt5_demo": "DEMO_VALIDADO",
            "real": "DESABILITADO",
        }
