"""End-to-end senior market-context orchestration.

This module is the composition point for observation, temporal context,
integrated market reading, senior reasoning and senior risk reasoning. It does
not decide or execute orders. No individual candle, indicator, strategy, news
item, score or subsystem can authorize an operation here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping
from uuid import uuid4

from data.models import Candle

from .integrated_market_reading import IntegratedMarketReader
from .senior_context_cycle import SeniorContextCycle, SeniorContextCycleBoundary
from .senior_market_intelligence import SeniorMarketIntelligenceBoundary
from .senior_market_reasoning import SeniorMarketReasoner
from .senior_risk_reasoning import RiskDomain, RiskObservation, SeniorRiskReasoner
from .temporal_market_context import TemporalMarketContextEngine
from .whole_graph_observation import WholeGraphObservationBoundary


@dataclass(frozen=True)
class SeniorContextInput:
    """Explicit upstream context supplied to one senior reasoning cycle."""

    context_id: str
    candles: tuple[Candle, ...]
    available_nodes: tuple[str, ...]
    observed_nodes: tuple[str, ...]
    gaps: Mapping[str, str]
    relationships_reviewed: tuple[str, ...]
    risk_observations: tuple[RiskObservation, ...]
    validated_knowledge_ids: tuple[str, ...] = ()
    available_risk_domains: tuple[RiskDomain, ...] = tuple(RiskDomain)


class SeniorContextOrchestrator:
    """Build one integrated, auditable senior context without execution authority.

    The orchestrator intentionally requires the caller to declare what context
    was available and what was observed. It never invents missing market data,
    risk facts or knowledge. The whole-graph boundary makes omissions explicit;
    temporal context relates history/present/scenarios; integrated reading joins
    independent evidence; senior reasoning challenges assumptions; and senior
    risk reasoning evaluates material risk in the same way for manual and
    autonomous modes.
    """

    def __init__(self) -> None:
        self.whole_graph = WholeGraphObservationBoundary()
        self.temporal = TemporalMarketContextEngine()
        self.reader = IntegratedMarketReader()
        self.reasoner = SeniorMarketReasoner()
        self.risk_reasoner = SeniorRiskReasoner()
        self.intelligence = SeniorMarketIntelligenceBoundary()
        self.cycle_boundary = SeniorContextCycleBoundary()

    def assess(self, request: SeniorContextInput) -> SeniorContextCycle:
        self._validate_input(request)
        graph = self.whole_graph.audit(
            context_id=request.context_id,
            available_nodes=request.available_nodes,
            observed_nodes=request.observed_nodes,
            gaps=request.gaps,
            relationships_reviewed=request.relationships_reviewed,
        )
        temporal = self.temporal.analyze(list(request.candles))
        reading = self.reader.read(list(request.candles))
        senior = self.reasoner.assess(list(request.candles), reading, temporal)
        risk = self.risk_reasoner.assess(
            request.risk_observations,
            available_domains=request.available_risk_domains,
        )
        intelligence = self.intelligence.assess(graph=graph)
        knowledge_ids = tuple(dict.fromkeys((*intelligence.knowledge_ids, *request.validated_knowledge_ids)))
        return self.cycle_boundary.assemble(
            cycle_id=str(uuid4()),
            whole_graph=graph,
            temporal_context=temporal,
            market_reading=reading,
            senior_assessment=senior,
            risk_assessment=risk,
            validated_knowledge_ids=knowledge_ids,
        )

    @staticmethod
    def _validate_input(request: SeniorContextInput) -> None:
        if not isinstance(request, SeniorContextInput):
            raise ValueError("request must be SeniorContextInput")
        if not request.context_id.strip():
            raise ValueError("context_id is required")
        if not request.candles:
            raise ValueError("candles are required")
        if any(not isinstance(candle, Candle) or not candle.is_valid() for candle in request.candles):
            raise ValueError("candles must contain valid Candle values")
        if any(request.candles[index].timestamp > request.candles[index + 1].timestamp for index in range(len(request.candles) - 1)):
            raise ValueError("candles must be ordered by timestamp")
        if not isinstance(request.gaps, Mapping):
            raise ValueError("gaps must be a mapping")
        if any(not isinstance(item, RiskObservation) for item in request.risk_observations):
            raise ValueError("risk_observations must contain RiskObservation values")
        for value in request.validated_knowledge_ids:
            if not isinstance(value, str) or not value.strip():
                raise ValueError("validated_knowledge_ids must contain non-empty strings")
        for domain in request.available_risk_domains:
            if not isinstance(domain, RiskDomain):
                raise ValueError("available_risk_domains must contain RiskDomain values")
