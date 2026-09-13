import pytest

from core.financial_market_curriculum import CurriculumModule, CurriculumStage, CurriculumDomain, SeniorFinancialMarketCurriculum
from core.senior_domain_expertise import DomainExpertiseStatus, SeniorDomainExpertiseRegistry
from core.senior_experience_profile import SeniorExperienceProfile
from core.senior_module_expertise import ModuleExpertiseStatus, SeniorModuleExpertiseRegistry


def test_all_current_curriculum_modules_receive_45_plus_advanced_capability():
    curriculum = SeniorFinancialMarketCurriculum()
    registry = SeniorModuleExpertiseRegistry()
    expertise = registry.resolve_all(curriculum)

    assert len(expertise) == len(curriculum.modules)
    assert all(item.experience_years >= 45 for item in expertise)
    assert all(item.experience_is_open_ended for item in expertise)
    assert all(item.execution_authorized is False for item in expertise)
    assert all(item.status is ModuleExpertiseStatus.CAPABILITY_READY for item in expertise)
    assert all(item.advanced_capabilities for item in expertise)


def test_profile_growth_is_not_capped_at_45_years():
    registry = SeniorModuleExpertiseRegistry(SeniorExperienceProfile(experience_years=60))
    module = SeniorFinancialMarketCurriculum().modules[0]

    expertise = registry.resolve(module)

    assert expertise.experience_years == 60
    assert expertise.experience_is_open_ended is True


def test_future_module_inherits_structure_but_requires_domain_validation():
    future = CurriculumModule(
        module_id="FM-NEW",
        title="Novo domínio de mercado",
        stage=CurriculumStage.CONTINUOUS_RESEARCH,
        domain=CurriculumDomain.CONTINUOUS_RESEARCH,
        prerequisites=(),
        topics=("novo instrumento", "nova infraestrutura"),
        practical_competencies=("avaliar o novo domínio",),
        senior_capabilities=("compreender estrutura, risco e evidência do novo domínio",),
    )

    expertise = SeniorModuleExpertiseRegistry().register_future_module(future)

    assert expertise.experience_years >= 45
    assert expertise.status is ModuleExpertiseStatus.REQUIRES_DOMAIN_VALIDATION
    assert expertise.execution_authorized is False


def test_known_asset_domains_have_advanced_professional_context():
    registry = SeniorDomainExpertiseRegistry()
    domains = ("forex", "indices", "equities", "etfs_funds_fiis", "commodities", "futures", "crypto", "fixed_income", "derivatives", "market_microstructure", "risk_management", "execution", "macro", "fundamental_analysis", "technical_price_action", "quantitative_statistics", "systematic_automation", "security", "research", "audit", "teaching_learning")

    for domain in domains:
        expertise = registry.resolve(domain)
        assert expertise.status is DomainExpertiseStatus.VERIFIED_BASELINE
        assert expertise.experience_years >= 45
        assert expertise.experience_is_open_ended is True
        assert expertise.competencies
        assert expertise.required_evidence
        assert expertise.is_operationally_eligible is True


def test_unknown_domain_does_not_fake_experience():
    expertise = SeniorDomainExpertiseRegistry().resolve("future_unknown_asset_class")

    assert expertise.status is DomainExpertiseStatus.REQUIRES_VALIDATION
    assert expertise.experience_years >= 45
    assert expertise.is_operationally_eligible is False
    assert expertise.execution_authorized if hasattr(expertise, "execution_authorized") else True
