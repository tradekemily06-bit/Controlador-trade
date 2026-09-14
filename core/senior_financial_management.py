"""Senior financial-management reasoning for the trading professional layer.

This is educational and analytical capability. It does not authorize trades,
transfers, withdrawals, leverage, or REAL execution.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum


class FinancialManagementDomain(str, Enum):
    CAPITAL = "CAPITAL"
    CASH_FLOW = "CASH_FLOW"
    BUDGET = "BUDGET"
    LIQUIDITY = "LIQUIDITY"
    POSITION_SIZING = "POSITION_SIZING"
    ALLOCATION = "ALLOCATION"
    CONCENTRATION = "CONCENTRATION"
    DRAWDOWN = "DRAWDOWN"
    LEVERAGE = "LEVERAGE"
    RESERVES = "RESERVES"
    COSTS = "COSTS"
    PERFORMANCE = "PERFORMANCE"
    TAX_AND_RECORDKEEPING = "TAX_AND_RECORDKEEPING"
    PORTFOLIO = "PORTFOLIO"
    CONTINGENCY = "CONTINGENCY"


@dataclass(frozen=True)
class SeniorFinancialManagementAssessment:
    domain: FinancialManagementDomain
    status: str
    findings: tuple[str, ...]
    execution_authorized: bool = False


def assess_financial_management(
    *,
    domain: FinancialManagementDomain,
    capital: Decimal,
    amount_at_risk: Decimal,
    liquid_reserve: Decimal,
    drawdown: Decimal = Decimal("0"),
    concentration: Decimal = Decimal("0"),
    leverage: Decimal = Decimal("1"),
) -> SeniorFinancialManagementAssessment:
    """Assess financial-management context; never produces execution authority."""
    values = (capital, amount_at_risk, liquid_reserve, drawdown, concentration, leverage)
    try:
        capital, amount_at_risk, liquid_reserve, drawdown, concentration, leverage = (Decimal(str(v)) for v in values)
    except Exception:
        return SeniorFinancialManagementAssessment(domain, "REASSESS", ("invalid_financial_numeric_input",))
    if not all(v.is_finite() for v in values):
        return SeniorFinancialManagementAssessment(domain, "REASSESS", ("non_finite_financial_input",))
    findings: list[str] = []
    if capital <= 0:
        findings.append("capital_must_be_positive")
    if amount_at_risk < 0 or liquid_reserve < 0 or drawdown < 0 or concentration < 0:
        findings.append("financial_amounts_must_be_non_negative")
    if leverage <= 0:
        findings.append("leverage_must_be_positive")
    if amount_at_risk > capital:
        findings.append("amount_at_risk_exceeds_available_capital")
    if liquid_reserve > capital:
        findings.append("liquid_reserve_exceeds_declared_capital")
    if drawdown >= capital and capital > 0:
        findings.append("drawdown_consumes_declared_capital")
    if concentration > Decimal("1"):
        findings.append("concentration_exceeds_full_capital_reference")
    return SeniorFinancialManagementAssessment(
        domain,
        "REASSESS" if findings else "ASSESSED",
        tuple(findings),
        execution_authorized=False,
    )
