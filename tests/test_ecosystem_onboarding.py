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
    assert all(step.technical_details_hidden for step in guide.steps)
