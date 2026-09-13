import pytest

from core.senior_experience_profile import ExperienceScope, SeniorExperienceProfile


def test_senior_profile_starts_with_45_plus_baseline_on_first_day():
    profile = SeniorExperienceProfile()
    profile.validate()
    assert profile.experience_years == 45
    assert profile.minimum_experience_years == 45
    assert profile.is_45_plus is True
    assert profile.first_day_with_user is True
    assert profile.experience_resets_on_assignment is False
    assert profile.experience_growth_enabled is True
    assert profile.experience_ceiling is None
    assert set(profile.scopes) == set(ExperienceScope)


def test_45_is_not_a_ceiling_and_higher_experience_is_valid():
    profile = SeniorExperienceProfile(experience_years=60)
    profile.validate()
    assert profile.is_45_plus is True
    assert profile.experience_years == 60
    assert profile.experience_ceiling is None


def test_assignment_never_reduces_professional_baseline():
    profile = SeniorExperienceProfile(experience_years=45, newly_assigned_to_user=True)
    posture = profile.professional_posture()
    assert "Use accumulated market knowledge before forming a conclusion." in posture
    assert "Treat 45+ years as a minimum professional baseline, never as a ceiling." in posture


def test_invalid_lower_baseline_reset_disabled_growth_or_ceiling_is_rejected():
    with pytest.raises(ValueError):
        SeniorExperienceProfile(experience_years=44).validate()
    with pytest.raises(ValueError):
        SeniorExperienceProfile(experience_resets_on_assignment=True).validate()
    with pytest.raises(ValueError):
        SeniorExperienceProfile(experience_growth_enabled=False).validate()
    with pytest.raises(ValueError):
        SeniorExperienceProfile(experience_ceiling=100).validate()
