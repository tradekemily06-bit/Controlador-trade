"""Completeness contract for the senior professional knowledge layer.

This contract closes an architectural gap between the broad market curriculum,
the advanced professional-depth catalog and the dedicated financial-management
reasoning layer. It does not grant execution authority.
"""
from __future__ import annotations

from dataclasses import dataclass

from .financial_market_curriculum import CurriculumDomain, SeniorFinancialMarketCurriculum
from .senior_financial_management import FinancialManagementDomain
from .senior_professional_depth import SeniorProfessionalDepth, build_senior_professional_depth


REQUIRED_PROFESSIONAL_DOMAINS: tuple[str, ...] = (
    "financial_accounting",
    "corporate_finance",
    "valuation",
    "treasury_and_cash_management",
    "tax_and_recordkeeping",
    "portfolio_risk",
    "derivatives_pricing",
    "market_microstructure",
    "technical_market_structure",
    "macro_and_geopolitics",
    "behavioral_finance",
    "quantitative_research",
    "machine_learning_for_markets",
    "data_engineering",
    "software_and_systems",
    "cybersecurity_and_identity",
    "operations_and_business_continuity",
    "regulation_and_compliance",
    "research_governance",
    "professional_communication",
    "crisis_and_tail_risk",
)

REQUIRED_FINANCIAL_MANAGEMENT_DOMAINS = frozenset(item.value.lower() for item in FinancialManagementDomain)


@dataclass(frozen=True)
class SeniorProfessionalCompleteness:
    domains: tuple[SeniorProfessionalDepth, ...]
    curriculum_domains: frozenset[CurriculumDomain]
    financial_management_domains: frozenset[str]
    experience_years: int = 45
    experience_is_open_ended: bool = True
    execution_authorized: bool = False

    def validate(self) -> None:
        if self.experience_years < 45:
            raise ValueError("senior professional baseline must remain 45+")
        if not self.experience_is_open_ended:
            raise ValueError("senior professional experience cannot have an upper ceiling")
        if self.execution_authorized:
            raise ValueError("professional completeness cannot authorize execution")
        domain_ids = {item.domain_id for item in self.domains}
        missing = set(REQUIRED_PROFESSIONAL_DOMAINS) - domain_ids
        if missing:
            raise ValueError(f"missing professional domains: {sorted(missing)}")
        for item in self.domains:
            item.validate()
        if not self.financial_management_domains.issuperset(REQUIRED_FINANCIAL_MANAGEMENT_DOMAINS):
            missing_financial = REQUIRED_FINANCIAL_MANAGEMENT_DOMAINS - self.financial_management_domains
            raise ValueError(f"missing financial-management domains: {sorted(missing_financial)}")
        # Funds and ETFs are explicitly covered inside the existing equities/
        # funds module, so completeness is checked by the curriculum's actual
        # modules rather than by an unused enum member.
        required_curriculum = {
            CurriculumDomain.PERSONAL_FINANCE,
            CurriculumDomain.FINANCIAL_SYSTEM,
            CurriculumDomain.FIXED_INCOME,
            CurriculumDomain.EQUITIES,
            CurriculumDomain.DERIVATIVES,
            CurriculumDomain.MARKET_MICROSTRUCTURE,
            CurriculumDomain.TECHNICAL_ANALYSIS,
            CurriculumDomain.FUNDAMENTAL_ANALYSIS,
            CurriculumDomain.MACROECONOMICS,
            CurriculumDomain.QUANTITATIVE_METHODS,
            CurriculumDomain.PORTFOLIO_CONSTRUCTION,
            CurriculumDomain.RISK_MANAGEMENT,
            CurriculumDomain.TRADING_METHODOLOGIES,
            CurriculumDomain.PSYCHOLOGY,
            CurriculumDomain.EXECUTION,
            CurriculumDomain.SYSTEMATIC_TRADING,
            CurriculumDomain.REGULATION_ETHICS,
            CurriculumDomain.CAREER_AND_PROFESSIONAL_PRACTICE,
            CurriculumDomain.CONTINUOUS_RESEARCH,
        }
        if not self.curriculum_domains.issuperset(required_curriculum):
            missing_curriculum = required_curriculum - self.curriculum_domains
            raise ValueError(f"missing curriculum domains: {sorted(item.value for item in missing_curriculum)}")


def build_senior_professional_completeness() -> SeniorProfessionalCompleteness:
    profile = SeniorProfessionalCompleteness(
        domains=build_senior_professional_depth(),
        curriculum_domains=frozenset(module.domain for module in SeniorFinancialMarketCurriculum().modules),
        financial_management_domains=REQUIRED_FINANCIAL_MANAGEMENT_DOMAINS,
    )
    profile.validate()
    return profile
