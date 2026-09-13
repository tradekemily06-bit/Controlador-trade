from core.financial_market_curriculum import (
    CurriculumDomain,
    CurriculumStage,
    SeniorFinancialMarketCurriculum,
)


def test_curriculum_covers_foundation_to_continuous_research():
    curriculum = SeniorFinancialMarketCurriculum()
    stages = {module.stage for module in curriculum.modules}

    assert CurriculumStage.FOUNDATION in stages
    assert CurriculumStage.INTERMEDIATE in stages
    assert CurriculumStage.ADVANCED in stages
    assert CurriculumStage.PROFESSIONAL in stages
    assert CurriculumStage.CONTINUOUS_RESEARCH in stages


def test_curriculum_covers_user_requested_financial_domains():
    curriculum = SeniorFinancialMarketCurriculum()
    domains = {module.domain for module in curriculum.modules}

    expected = {
        CurriculumDomain.PERSONAL_FINANCE,
        CurriculumDomain.FINANCIAL_SYSTEM,
        CurriculumDomain.FIXED_INCOME,
        CurriculumDomain.EQUITIES,
        CurriculumDomain.FUNDS_ETFS,
        CurriculumDomain.DERIVATIVES,
        CurriculumDomain.TECHNICAL_ANALYSIS,
        CurriculumDomain.FUNDAMENTAL_ANALYSIS,
        CurriculumDomain.MACROECONOMICS,
        CurriculumDomain.QUANTITATIVE_METHODS,
        CurriculumDomain.PORTFOLIO_CONSTRUCTION,
        CurriculumDomain.RISK_MANAGEMENT,
        CurriculumDomain.TRADING_METHODOLOGIES,
        CurriculumDomain.PSYCHOLOGY,
        CurriculumDomain.EXECUTION,
        CurriculumDomain.SYSTEMATIC_TRADING,
        CurriculumDomain.REGULATION_ETHICS,
        CurriculumDomain.CAREER_AND_PROFESSIONAL_PRACTICE,
    }
    assert expected <= domains


def test_each_module_has_senior_depth_and_never_authorizes_execution():
    curriculum = SeniorFinancialMarketCurriculum()

    assert curriculum.modules
    for module in curriculum.modules:
        assert module.topics
        assert module.practical_competencies
        assert module.senior_capabilities
        assert module.requires_validation is True
        assert module.execution_authorized is False


def test_domain_lookup_and_module_lookup_are_traceable():
    curriculum = SeniorFinancialMarketCurriculum()

    risk_modules = curriculum.by_domain(CurriculumDomain.RISK_MANAGEMENT)
    assert len(risk_modules) == 1
    assert curriculum.get(risk_modules[0].module_id) is risk_modules[0]
