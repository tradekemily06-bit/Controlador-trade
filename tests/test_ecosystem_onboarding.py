from core.ecosystem_onboarding import EcosystemOnboarding, OnboardingSection


def test_first_use_guide_maps_main_capabilities_without_execution_authority():
    guide = EcosystemOnboarding().build_first_use_guide()

    assert guide.execution_authorized is False
    assert guide.steps
    locations = {step.location for step in guide.steps}
    assert OnboardingSection.OPERATION in locations
    assert OnboardingSection.ANALYSIS in locations
    assert OnboardingSection.LEARNING in locations
    assert OnboardingSection.RISK in locations
    assert OnboardingSection.SECURITY in locations
    assert OnboardingSection.RECOVERY in locations
    assert all(step.technical_details_hidden for step in guide.steps)


def test_recovery_step_teaches_revalidation_and_no_safety_bypass():
    guide = EcosystemOnboarding().build_first_use_guide()
    recovery = next(step for step in guide.steps if step.location is OnboardingSection.RECOVERY)

    assert "correções" in recovery.purpose.lower()
    assert "revalida" in recovery.purpose.lower()
    assert "contornar" in recovery.action_hint.lower()
