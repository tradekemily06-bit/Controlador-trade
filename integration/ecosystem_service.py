from __future__ import annotations

from dataclasses import asdict
from typing import Any, Iterable

from analysis.decision_record import DecisionRecord
from analysis.decision_store import DecisionStore
from analysis.statistics import summarize, summarize_breakdowns, summarize_periods
from core.risk_manager import RiskManager
from core.signal_engine import SignalEngine
from integration.news_provider import UnconfiguredNewsProvider
from security.identity_boundary import IdentityPolicy
from security.request_context import ProductionRequestContext, require_production_context
from storage.production_boundary import ProductionStoragePolicy


class EcosystemService:
    """Application orchestration; broker execution remains outside this layer."""

    def __init__(
        self,
        engine: SignalEngine | None = None,
        decision_store: DecisionStore | None = None,
        production_storage: ProductionStoragePolicy | None = None,
    ) -> None:
        self.engine = engine or SignalEngine()
        self.store = decision_store or DecisionStore()
        self.memory: list[DecisionRecord] = self.store.load()
        self.risk = RiskManager()
        self.news = UnconfiguredNewsProvider()
        self.identity = IdentityPolicy()
        # Production readiness is an explicit deployment boundary. Local SQLite
        # persistence must never be treated as tenant-scoped durable production storage.
        self.production_storage = production_storage or ProductionStoragePolicy()

    def require_production_context(self, *, subject_id: str | None, tenant_id: str | None) -> ProductionRequestContext:
        """Return trusted production scope or fail closed before protected operations."""
        return require_production_context(subject_id=subject_id, tenant_id=tenant_id)

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
        self.store.save(record)
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
                self.store.save(updated)
                return updated
        raise ValueError("decision_id não encontrado")

    def statistics(self) -> dict[str, Any]:
        breakdowns = summarize_breakdowns(self.memory)
        return {
            **asdict(summarize(self.memory)),
            "periods": summarize_periods(self.memory),
            "breakdowns": {
                **breakdowns,
                "by_symbol": breakdowns["symbols"],
                "by_timeframe": breakdowns["timeframes"],
                "by_signal": breakdowns["signals"],
                "by_score_band": breakdowns["score_bands"],
            },
        }

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
            "memory_persistence": "SQLITE" if self.store.database_path else "IN_MEMORY",
            "production_storage": self.production_storage.status(),
            "replay": "ONLINE",
            "statistics": "ONLINE",
            "risk_gate": "ONLINE",
            "news": "AGUARDANDO_FONTE",
            "mt5_demo": "DEMO_VALIDADO",
            "real": "DESABILITADO",
            **self.identity.status(),
        }
