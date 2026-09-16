"""Open-ended advanced depth profile for the senior professional layer.

This catalog deliberately goes beyond the user's initial curriculum list. It
covers adjacent disciplines a genuinely experienced market professional needs
in order to reason safely: accounting, valuation, treasury, taxation,
portfolio construction, derivatives, data, research, technology, operations,
security, regulation and crisis management.

The 45+ value is an experience baseline, not a fabricated biography or
credential. There is no upper ceiling and no execution authority.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping


class ProfessionalDepth(str, Enum):
    ADVANCED = "ADVANCED"
    EXPERT = "EXPERT"
    CONTINUOUS_RESEARCH = "CONTINUOUS_RESEARCH"


@dataclass(frozen=True)
class SeniorProfessionalDepth:
    domain_id: str
    depth: ProfessionalDepth
    experience_years: int = 45
    experience_is_open_ended: bool = True
    competencies: tuple[str, ...] = ()
    evidence_requirements: tuple[str, ...] = ()
    execution_authorized: bool = False

    def validate(self) -> None:
        if not self.domain_id.strip():
            raise ValueError("professional depth domain is required")
        if self.experience_years < 45:
            raise ValueError("professional depth must preserve the 45+ baseline")
        if not self.experience_is_open_ended:
            raise ValueError("professional experience cannot have an upper ceiling")
        if not self.competencies or not self.evidence_requirements:
            raise ValueError("advanced competencies and evidence requirements are required")
        if self.execution_authorized:
            raise ValueError("professional knowledge cannot authorize execution")


_COMMON_EVIDENCE = (
    "authoritative and current source material appropriate to the domain",
    "historical context and regime changes",
    "independent evidence plus explicit counterevidence",
    "reproducible tests, scenarios or case studies",
    "data-quality, provenance and uncertainty assessment",
    "jurisdiction/session/instrument context when applicable",
)

_DEPTH: Mapping[str, tuple[str, ...]] = {
    "financial_accounting": (
        "financial statements, notes, accounting policies and quality of earnings",
        "working capital, cash conversion, accruals, provisions and off-balance-sheet exposure",
        "earnings quality, manipulation indicators and accounting red flags",
        "IFRS/GAAP differences and jurisdiction-aware interpretation",
    ),
    "corporate_finance": (
        "capital structure, cost of capital and financing choices",
        "capital allocation, buybacks, dividends and reinvestment economics",
        "M&A, restructuring, insolvency and stakeholder incentives",
        "free cash flow, economic profit and value creation/destruction",
    ),
    "valuation": (
        "DCF, multiples, residual income and asset-based valuation",
        "scenario analysis, sensitivity, terminal value and margin of safety",
        "expectations embedded in price and valuation dispersion",
        "valuation under changing rates, risk premia and regimes",
    ),
    "treasury_and_cash_management": (
        "cash forecasting, liquidity ladders and contingency funding",
        "working-capital cycles, funding costs and refinancing risk",
        "currency exposure, hedging and cash concentration",
        "liquidity under stress and survival planning",
    ),
    "tax_and_recordkeeping": (
        "tax-aware investment and trading recordkeeping",
        "cost basis, realized versus unrealized results and reporting workflows",
        "jurisdiction-specific tax rules as time-sensitive external knowledge",
        "separation of educational analysis from regulated tax advice",
    ),
    "portfolio_risk": (
        "factor exposures, beta, duration, convexity and tail dependencies",
        "VaR/expected shortfall as analytical tools with model limitations",
        "stress testing, scenario analysis and drawdown decomposition",
        "liquidity-adjusted risk and concentration under correlated stress",
    ),
    "derivatives_pricing": (
        "no-arbitrage, forwards, futures, options and swap valuation",
        "Greeks, volatility surfaces, skew, term structure and smile dynamics",
        "hedging error, gap risk, basis risk and model risk",
        "collateral, margin, clearing and counterparty exposure",
    ),
    "market_microstructure": (
        "price discovery, order books, queue position and adverse selection",
        "spread, depth, market impact, liquidity fragmentation and venue quality",
        "auction/open/close mechanics and session transitions",
        "latency, data quality and execution-cost measurement",
    ),
    "technical_market_structure": (
        "trend, range, regime, swing structure and multi-timeframe context",
        "candles, wicks, rejection, breakouts, pullbacks and failed breakouts",
        "support/resistance and volume as contextual evidence rather than certainty",
        "user-defined price-action concepts including GAB, DDT, pressão, retirada de pavio and taxa dívida",
        "hypothesis testing of patterns without turning anecdotes into universal rules",
    ),
    "macro_and_geopolitics": (
        "monetary policy reaction functions and transmission mechanisms",
        "inflation, labor, growth, credit and liquidity cycles",
        "fiscal policy, sovereign financing and cross-country divergence",
        "geopolitical, commodity, sanctions and supply-chain transmission channels",
    ),
    "behavioral_finance": (
        "loss aversion, anchoring, confirmation bias and overconfidence",
        "herding, reflexivity, FOMO, panic and revenge behavior",
        "decision quality versus outcome quality",
        "process design that reduces emotional and cognitive failure modes",
    ),
    "quantitative_research": (
        "probability, statistics, inference and uncertainty calibration",
        "sampling bias, survivorship bias, look-ahead bias and data snooping",
        "multiple testing, overfitting, robustness and out-of-sample validation",
        "regime dependence, non-stationarity and parameter sensitivity",
    ),
    "machine_learning_for_markets": (
        "feature leakage, temporal validation and walk-forward evaluation",
        "model calibration, drift, interpretability and uncertainty",
        "class imbalance, false discovery and economic significance versus statistical significance",
        "safe separation of research models from operational authority",
    ),
    "data_engineering": (
        "market-data schemas, timestamps, corporate actions and instrument identity",
        "data lineage, provenance, versioning and reproducibility",
        "missing, stale, duplicated, out-of-order and conflicting data",
        "historical reconstruction and replay fidelity",
    ),
    "software_and_systems": (
        "state machines, deterministic pipelines and idempotency",
        "testing strategy, property testing, regression prevention and observability",
        "deployment, rollback, disaster recovery and controlled change",
        "API contracts, provider failure and reconciliation",
    ),
    "cybersecurity_and_identity": (
        "authentication, authorization, least privilege and tenant isolation",
        "secrets management, secure transport and session security",
        "supply-chain, dependency, logging and incident-response risk",
        "fail-closed behavior and recovery without exposing sensitive state",
    ),
    "operations_and_business_continuity": (
        "incident management, escalation and recovery objectives",
        "capacity based on actual resource cost rather than arbitrary product ceilings",
        "backup, restore, reconciliation and operational runbooks",
        "service health, degraded modes and safe shutdown",
    ),
    "regulation_and_compliance": (
        "jurisdiction-aware regulatory research and change monitoring",
        "market conduct, suitability, conflicts and recordkeeping",
        "AML/CTF, privacy, consumer protection and data governance",
        "distinguishing educational information from regulated professional advice",
    ),
    "research_governance": (
        "source hierarchy, provenance and claim tracking",
        "hypothesis, falsification, replication and counterevidence",
        "change control for knowledge that can affect analysis",
        "explicit uncertainty and reassessment when evidence changes",
    ),
    "professional_communication": (
        "explain complex financial reasoning from beginner to expert level",
        "communicate uncertainty without false precision",
        "document assumptions, risks, evidence and alternatives",
        "teach practical cases while preserving the distinction between learning and execution",
    ),
    "crisis_and_tail_risk": (
        "market crashes, flash events, gaps and liquidity disappearance",
        "counterparty failure, broker outage and infrastructure disruption",
        "contingency plans, kill switches and reconciliation of unknown states",
        "post-event forensic analysis and permanent control improvement",
    ),
}


def build_senior_professional_depth() -> tuple[SeniorProfessionalDepth, ...]:
    result = tuple(
        SeniorProfessionalDepth(
            domain_id=domain,
            depth=ProfessionalDepth.EXPERT,
            competencies=competencies,
            evidence_requirements=_COMMON_EVIDENCE,
        )
        for domain, competencies in _DEPTH.items()
    )
    for item in result:
        item.validate()
    return result


def get_senior_professional_depth(domain_id: str) -> SeniorProfessionalDepth:
    for item in build_senior_professional_depth():
        if item.domain_id == domain_id.strip().lower():
            return item
    raise KeyError(domain_id)
