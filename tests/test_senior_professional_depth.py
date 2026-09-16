from core.senior_knowledge_matrix import KnowledgeStatus, SeniorProfessionalKnowledgeMatrix
from core.senior_professional_depth import build_senior_professional_depth, get_senior_professional_depth


def test_advanced_depth_covers_adjacent_professional_disciplines():
    depths = build_senior_professional_depth()
    domains = {item.domain_id for item in depths}
    required = {
        "financial_accounting",
        "corporate_finance",
        "valuation",
        "treasury_and_cash_management",
        "tax_and_recordkeeping",
        "portfolio_risk",
        "derivatives_pricing",
        "market_microstructure",
        "machine_learning_for_markets",
        "data_engineering",
        "software_and_systems",
        "cybersecurity_and_identity",
        "operations_and_business_continuity",
        "regulation_and_compliance",
        "crisis_and_tail_risk",
    }
    assert required <= domains
    assert all(item.experience_years >= 45 for item in depths)
    assert all(item.experience_is_open_ended for item in depths)
    assert all(not item.execution_authorized for item in depths)


def test_knowledge_matrix_includes_advanced_depth_with_45_plus_baseline():
    matrix = SeniorProfessionalKnowledgeMatrix()
    records = [r for r in matrix.records if r.module_id.startswith("DEPTH-")]
    assert records
    assert all(r.experience_years >= 45 for r in records)
    assert all(r.experience_is_open_ended for r in records)
    assert all(r.status is KnowledgeStatus.UNVALIDATED for r in records)
    assert all(not r.execution_authorized for r in records)


def test_depth_unknown_domain_is_not_silently_invented():
    try:
        get_senior_professional_depth("unknown_future_domain")
    except KeyError:
        pass
    else:
        raise AssertionError("unknown future domains must require explicit registration/validation")
