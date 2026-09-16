from decimal import Decimal

from core.senior_financial_management import FinancialManagementDomain, assess_financial_management


def test_senior_financial_management_assesses_capital_and_risk_without_authority():
    result = assess_financial_management(
        domain=FinancialManagementDomain.CAPITAL,
        capital=Decimal("10000"),
        amount_at_risk=Decimal("100"),
        liquid_reserve=Decimal("3000"),
        leverage=Decimal("2"),
    )
    assert result.status == "ASSESSED"
    assert result.execution_authorized is False


def test_financial_management_reassesses_inconsistent_capital_context():
    result = assess_financial_management(
        domain=FinancialManagementDomain.ALLOCATION,
        capital=Decimal("1000"),
        amount_at_risk=Decimal("1200"),
        liquid_reserve=Decimal("100"),
    )
    assert result.status == "REASSESS"
    assert "amount_at_risk_exceeds_available_capital" in result.findings
