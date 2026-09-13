from core.risk_manager import RiskDecision
from core.senior_risk_gate import SeniorRiskGate
from core.senior_risk_reasoning import RiskDomain, RiskKnowledgeStatus, RiskObservation, SeniorRiskAssessment


def assessed_risk() -> SeniorRiskAssessment:
    return SeniorRiskAssessment(
        status=RiskKnowledgeStatus.ASSESSED,
        observations=(RiskObservation(RiskDomain.CAPITAL, "capital observado", True),),
        material_risks=("capital observado",),
        unknowns=(),
        questions=(),
        reassessment_triggers=(),
        execution_authorized=False,
    )


def test_gate_requires_both_senior_and_operational_risk_approval():
    result = SeniorRiskGate().evaluate(
        senior_risk=assessed_risk(),
        operational_risk=RiskDecision(True, "ok"),
    )
    assert result.allowed is True


def test_gate_blocks_when_senior_risk_requires_reassessment():
    risk = assessed_risk()
    incomplete = SeniorRiskAssessment(
        status=RiskKnowledgeStatus.REASSESS,
        observations=risk.observations,
        material_risks=risk.material_risks,
        unknowns=("LIQUIDITY",),
        questions=("liquidez?",),
        reassessment_triggers=("mudança",),
        execution_authorized=False,
    )
    result = SeniorRiskGate().evaluate(
        senior_risk=incomplete,
        operational_risk=RiskDecision(True, "ok"),
    )
    assert result.allowed is False


def test_gate_preserves_operational_risk_block():
    result = SeniorRiskGate().evaluate(
        senior_risk=assessed_risk(),
        operational_risk=RiskDecision(False, "limite atingido"),
    )
    assert result.allowed is False
    assert result.reason == "limite atingido"


def test_gate_never_accepts_execution_authority_from_senior_risk():
    risk = assessed_risk()
    unauthorized = SeniorRiskAssessment(
        status=risk.status,
        observations=risk.observations,
        material_risks=risk.material_risks,
        unknowns=risk.unknowns,
        questions=risk.questions,
        reassessment_triggers=risk.reassessment_triggers,
        execution_authorized=True,
    )
    result = SeniorRiskGate().evaluate(
        senior_risk=unauthorized,
        operational_risk=RiskDecision(True, "ok"),
    )
    assert result.allowed is False
