"""Advanced, open-ended financial-management curriculum for the senior layer.

The senior capability is analytical and educational only. It never grants
execution, withdrawal, transfer, or REAL-trading authority.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FinancialManagementDepth:
    domain_id: str = "financial_management"
    experience_years: int = 45
    experience_is_open_ended: bool = True
    execution_authorized: bool = False
    competencies: tuple[str, ...] = (
        "capital preservation, capital-at-risk and survival-first planning",
        "personal and trading cash-flow planning, budgeting and liquidity ladders",
        "manual operation financial discipline before, during and after an operation",
        "position sizing, allocation, concentration and portfolio interaction",
        "drawdown measurement, recovery math and risk-of-ruin reasoning",
        "leverage, margin, collateral and exposure without double-counting leverage",
        "reserves, emergency liquidity and contingency funding decisions",
        "transaction costs, spread, commissions, financing, slippage and market impact",
        "performance attribution, expectancy, variance, drawdown and process quality",
        "tax-aware recordkeeping, cost basis and jurisdiction-sensitive reporting research",
        "portfolio-level capital allocation and correlation-aware exposure management",
        "stress testing, crisis planning and post-event financial reconstruction",
    )

    def validate(self) -> None:
        if self.experience_years < 45:
            raise ValueError("financial-management depth must preserve the 45+ baseline")
        if not self.experience_is_open_ended:
            raise ValueError("financial-management experience cannot have an upper ceiling")
        if self.execution_authorized:
            raise ValueError("financial-management knowledge cannot authorize execution")
        if not self.competencies:
            raise ValueError("financial-management competencies are required")


def build_financial_management_depth() -> FinancialManagementDepth:
    profile = FinancialManagementDepth()
    profile.validate()
    return profile
