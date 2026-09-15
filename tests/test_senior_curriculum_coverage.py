from core.senior_curriculum_coverage import build_senior_curriculum_coverage


def test_senior_curriculum_includes_financial_management_and_allows_no_ceiling():
    coverage = build_senior_curriculum_coverage()
    assert "financial_management" in coverage.domains
    assert coverage.experience_years >= 45
    assert coverage.experience_is_open_ended is True
    assert coverage.execution_authorized is False


def test_senior_curriculum_has_no_execution_authority_in_any_domain():
    coverage = build_senior_curriculum_coverage()
    assert coverage.execution_authorized is False
