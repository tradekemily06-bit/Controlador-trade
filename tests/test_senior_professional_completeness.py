from core.senior_professional_completeness import build_senior_professional_completeness


def test_senior_professional_layer_is_complete_and_non_executable():
    profile = build_senior_professional_completeness()
    assert profile.experience_years >= 45
    assert profile.experience_is_open_ended is True
    assert profile.execution_authorized is False
    assert all(item.experience_years >= 45 for item in profile.domains)
    assert all(item.experience_is_open_ended for item in profile.domains)
    assert all(item.execution_authorized is False for item in profile.domains)
    assert profile.financial_management_domains
