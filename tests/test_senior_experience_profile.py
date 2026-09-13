import pytest

from core.senior_experience_profile import ExperienceScope, SeniorExperienceProfile


def test_senior_profile_starts_with_45_year_baseline_on_first_day():
    profile = SeniorExperienceProfile()
    profile.validate()
    assert profile.experience_years == 45
    assert profile.first_day_with_user is True
    assert profile.experience_resets_on_assignment is False
    assert set(profile.scopes) == set(ExperienceScope)


def test_assignment_never_reduces_professional_baseline():
    profile = SeniorExperienceProfile(experience_years=45, newly_assigned_to_user=True)
    assert "Use accumulated market knowledge before forming a conclusion." in profile.professional_posture()


def test_invalid_reset_or_lower_baseline_is_rejected():
    with pytest.raises(ValueError):
        SeniorExperienceProfile(experience_years=44).validate()
    with pytest.raises(ValueError):
        SeniorExperienceProfile(experience_resets_on_assignment=True).validate()
