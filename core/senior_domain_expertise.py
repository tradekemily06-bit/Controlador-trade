"""Open-ended senior expertise across assets, disciplines and ecosystem modules.

This is a capability contract, not a claim of omniscience or a fixed strategy
catalog. Every known domain inherits the ecosystem's 45+ professional baseline,
while domain-specific competencies describe what an advanced professional must
understand before that domain can materially influence an operational reading.
Unknown or newly added domains are explicitly marked for validation instead of
being treated as if the system already had verified expertise.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Mapping
from .senior_experience_profile import SeniorExperienceProfile

class DomainExpertiseStatus(str, Enum):
    VERIFIED_BASELINE = "VERIFIED_BASELINE"
    REQUIRES_VALIDATION = "REQUIRES_VALIDATION"

@dataclass(frozen=True)
class SeniorDomainExpertise:
    domain_id: str
    experience_years: int = 45
    status: DomainExpertiseStatus = DomainExpertiseStatus.VERIFIED_BASELINE
    asset_context: tuple[str, ...] = ()
    competencies: tuple[str, ...] = ()
    required_evidence: tuple[str, ...] = ()
    experience_is_open_ended: bool = True
    def validate(self) -> None:
        if not isinstance(self.domain_id, str) or not self.domain_id.strip(): raise ValueError("domain_id is required")
        if self.experience_years < 45: raise ValueError("domain expertise must preserve the 45+ baseline")
        if not self.experience_is_open_ended: raise ValueError("domain expertise cannot impose an upper experience ceiling")
        if not self.competencies: raise ValueError("advanced domain competencies are required")
        if not self.required_evidence: raise ValueError("domain evidence requirements are required")
    @property
    def is_operationally_eligible(self) -> bool:
        self.validate(); return self.status is DomainExpertiseStatus.VERIFIED_BASELINE

_COMMON_COMPETENCIES = (
    "Understand the domain's structure, participants, liquidity and price formation.",
    "Read historical regimes and distinguish them from the present market state.",
    "Evaluate volatility, liquidity, spreads, costs, slippage and execution conditions.",
    "Compare independent evidence with counterevidence and unresolved uncertainty.",
    "Recognize correlations, concentration and cross-asset transmission channels.",
    "Reassess when market regime, data quality or assumptions materially change.",
)
_COMMON_EVIDENCE = (
    "Current and historical market data appropriate to the domain.",
    "Relevant session, liquidity and execution conditions when applicable.",
    "Independent evidence plus explicit counterevidence and data-quality status.",
    "Validated domain knowledge with provenance and test history before operational reuse.",
)
_DOMAIN_DETAILS: Mapping[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "forex": (("currency pairs, sessions, liquidity pools and dealer/ECN microstructure", "central-bank and macro drivers", "carry, funding and cross-currency relationships", "spread, rollover and execution around session transitions"),("spot/forward market context", "session and liquidity state", "macro/currency divergence", "funding and transaction costs")),
    "indices": (("index construction and constituent effects", "cash/futures relationships", "session opens, closes and gap behavior", "breadth, volatility and index-specific liquidity"),("index composition and concentration", "cash-versus-derivative context", "session/gap conditions")),
    "equities": (("company-specific catalysts", "earnings, guidance and corporate actions", "order-book/liquidity conditions", "sector and factor exposures"),("fundamental and event evidence", "corporate-action state", "liquidity and spread conditions")),
    "etfs_funds_fiis": (("fund structure, holdings and methodology", "NAV versus traded price and liquidity", "creation/redemption or fund-specific mechanics", "distribution, fees and tracking behavior"),("fund methodology and holdings", "NAV/liquidity relationship", "fees, distributions and tracking quality")),
    "commodities": (("physical supply/demand and inventory dynamics", "seasonality and production constraints", "futures curves and roll structure", "weather, geopolitics and transport/logistics shocks"),("inventory/supply-demand evidence", "curve and roll state", "event and geopolitical risk")),
    "futures": (("contract specifications and expiry", "basis, term structure and roll behavior", "margin, leverage and liquidation mechanics", "session-specific liquidity and order-flow conditions"),("contract and expiry metadata", "basis/curve state", "margin and liquidity conditions")),
    "crypto": (("24/7 fragmented venues and liquidity", "funding, basis and derivatives positioning", "on-chain and protocol-specific drivers when relevant", "exchange, custody and counterparty risks"),("venue and liquidity quality", "funding/basis context", "counterparty and infrastructure status")),
    "fixed_income": (("yield curves, duration and convexity", "credit and sovereign risk", "central-bank policy and term premia", "liquidity and pricing differences across instruments"),("curve and rate evidence", "credit/sovereign context", "duration and liquidity sensitivity")),
    "derivatives": (("contract payoff and nonlinear exposure", "implied versus realized volatility", "Greeks and scenario sensitivity", "margin, collateral, counterparty and settlement mechanics"),("contract specification", "volatility surface or relevant pricing state", "margin/collateral and counterparty conditions")),
    "market_microstructure": (("order-book dynamics and liquidity", "price discovery and execution quality", "spread, depth, impact and adverse selection", "venue fragmentation and latency-sensitive conditions"),("depth/liquidity evidence", "execution-quality measurements", "venue and data-quality provenance")),
    "risk_management": (("capital, exposure, drawdown and leverage", "concentration and correlation", "liquidity, slippage, costs and volatility", "model, data, counterparty, operational, security and recovery risk"),("complete risk-domain assessment", "current exposure and limits", "stress and recovery evidence")),
    "execution": (("order lifecycle and state reconciliation", "broker/provider constraints", "slippage, latency, rejection, duplicate and disconnect handling", "fail-safe recovery and auditability"),("authoritative order/position state", "provider constraints", "reconciliation and recovery evidence")),
    "macro": (("monetary and fiscal policy", "inflation, employment, growth and liquidity cycles", "cross-country divergence and capital flows", "event risk and regime transitions"),("current macro releases and policy context", "cross-asset confirmation", "event calendar and regime evidence")),
    "fundamental_analysis": (("financial statements and business quality", "valuation and expectations", "earnings, guidance and catalysts", "industry structure and competitive dynamics"),("primary financial/event evidence", "expectation versus realized outcome", "valuation and business-quality evidence")),
    "technical_price_action": (("market structure, trend, range and regime", "candles, price action and contextual patterns", "support/resistance, breakouts and pullbacks as observations", "multi-timeframe relationships without isolated-signal authority"),("closed-candle evidence", "structural context", "independent confluence and counterevidence")),
    "quantitative_statistics": (("probability, distributions and statistical inference", "sampling, bias and overfitting", "regime sensitivity and robustness", "uncertainty, calibration and out-of-sample validation"),("validated datasets", "statistical assumptions", "robustness and out-of-sample evidence")),
    "systematic_automation": (("deterministic pipelines and state machines", "data lineage and reproducibility", "failure modes, idempotency and recovery", "deployment, monitoring and controlled change"),("reproducible inputs/outputs", "test and audit evidence", "failure/recovery validation")),
    "security": (("identity, authorization and least privilege", "secret isolation and transport security", "supply-chain and dependency risk", "auditability, incident response and recovery"),("authorization provenance", "dependency/security evidence", "incident and recovery evidence")),
    "research": (("source quality and provenance", "hypothesis formation and falsification", "independent corroboration", "safe incorporation of new knowledge without silently changing operational authority"),("trusted source provenance", "claim and counterclaim evidence", "validation/test results")),
    "audit": (("traceability from input to decision and outcome", "completeness and consistency checks", "reconciliation of expected versus actual state", "root-cause analysis and regression prevention"),("complete audit trail", "independent reconciliation", "regression evidence")),
    "teaching_learning": (("progressive explanation from foundation to advanced practice", "distinguish fact, hypothesis and validated knowledge", "design of practical tests and replay exercises", "learning from outcomes without turning anecdotes into rules"),("validated educational sources", "learner activity/results", "knowledge provenance and validation status")),
}

def _build(domain_id: str, *, status=DomainExpertiseStatus.VERIFIED_BASELINE) -> SeniorDomainExpertise:
    details = _DOMAIN_DETAILS.get(domain_id)
    if details is None: return SeniorDomainExpertise(domain_id=domain_id, status=DomainExpertiseStatus.REQUIRES_VALIDATION, competencies=_COMMON_COMPETENCIES, required_evidence=_COMMON_EVIDENCE)
    result = SeniorDomainExpertise(domain_id=domain_id, status=status, asset_context=details[0], competencies=_COMMON_COMPETENCIES + details[0], required_evidence=_COMMON_EVIDENCE + details[1])
    result.validate(); return result

class SeniorDomainExpertiseRegistry:
    def __init__(self, profile: SeniorExperienceProfile | None = None):
        self.profile = profile or SeniorExperienceProfile(); self.profile.validate(); self._domains = {domain_id: _build(domain_id) for domain_id in _DOMAIN_DETAILS}
    def resolve(self, domain_id: str) -> SeniorDomainExpertise:
        if not isinstance(domain_id, str) or not domain_id.strip(): raise ValueError("domain_id is required")
        key = domain_id.strip().lower(); known = self._domains.get(key)
        if known is None: return _build(key, status=DomainExpertiseStatus.REQUIRES_VALIDATION)
        if self.profile.experience_years <= known.experience_years: return known
        return SeniorDomainExpertise(domain_id=known.domain_id, experience_years=self.profile.experience_years, status=known.status, asset_context=known.asset_context, competencies=known.competencies, required_evidence=known.required_evidence)
    def register(self, expertise: SeniorDomainExpertise) -> None:
        if not isinstance(expertise, SeniorDomainExpertise): raise ValueError("expertise must be SeniorDomainExpertise")
        expertise.validate(); self._domains[expertise.domain_id.strip().lower()] = expertise
    def current_domains(self) -> tuple[str, ...]: return tuple(sorted(self._domains))
    def resolve_many(self, domain_ids: Iterable[str]) -> tuple[SeniorDomainExpertise, ...]: return tuple(self.resolve(domain_id) for domain_id in domain_ids)
