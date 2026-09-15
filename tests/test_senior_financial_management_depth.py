from core.senior_financial_management_depth import build_financial_management_depth


def test_financial_management_is_advanced_and_open_ended():
    profile = build_financial_management_depth()
    assert profile.experience_years >= 45
    assert profile.experience_is_open_ended is True
    assert len(profile.competencies) >= 10
    assert profile.execution_authorized is False


def test_financial_management_includes_manual_operation_and_capital_survival():
    profile = build_financial_management_depth()
    text = " ".join(profile.competencies).lower()
    assert "manual operation" in text
    assert "capital preservation" in text
    assert "drawdown" in text
    assert "leverage" in text
    assert "tax-aware" in text
