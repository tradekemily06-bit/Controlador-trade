import pytest

from core.senior_experience_profile import ExperienceScope, SeniorExperienceProfile


def test_senior_profile_starts_with_45_plus_baseline_on_first_day():
    profile = SeniorExperienceProfile()
    profile.validate()
    assert profile.experience_years == 45
    assert profile.is_45_plus is True
    assert profile.first_day_with_user is True
    assert profile.experience_resets_on_assignment is False
    assert set(profile.scopes) == set(ExperienceScope)


def test_experience_above_45_remains_valid_without_an_upper_ceiling():
    profile = SeniorExperienceProfile(experience_years=60, newly_assigned_to_user=True)
    profile.validate()
    assert profile.is_45_plus is True
    assert "Continue capability growth without an artificial upper experience limit." in profile.professional_posture()


def test_assignment_never_reduces_professional_baseline():
    profile = SeniorExperienceProfile(experience_years=45, newly_assigned_to_user=True)
    assert "Use accumulated market knowledge before forming a conclusion." in profile.professional_posture()


def test_invalid_reset_or_lower_baseline_is_rejected():
    with pytest.raises(ValueError):
        SeniorExperienceProfile(experience_years=44).validate()
    with pytest.raises(ValueError):
        SeniorExperienceProfile(experience_resets_on_assignment=True).validate()
