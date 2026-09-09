import pytest
from core.p105_operational_hypothesis_admission import OperationalHypothesisAdmission
from core.p106_operational_hypothesis_audit import OperationalHypothesisAuditBoundary
from core.p107_operational_validation_specification import OperationalValidationSpecificationBoundary
from core.p108_operational_validation_run import OperationalValidationRunBoundary
from core.p109_operational_validation_result import OperationalValidationResultBoundary
from core.p110_operational_validation_decision import OperationalValidationDecisionBoundary

def admission():
    return OperationalHypothesisAdmission("ad105", "h104", "ctx103", "r102")

def test_p106_p110_flow_and_provenance():
    a=OperationalHypothesisAuditBoundary().audit(admission(), audit_id="a106", rationale="verified")
    s=OperationalValidationSpecificationBoundary().specify(a, specification_id="s107", test_id="t107", environment="LAB", criteria="explicit")
    r=OperationalValidationRunBoundary().record(s, run_id="r108", sample_size=10, observation="observed")
    result=OperationalValidationResultBoundary().conclude(r, result_id="res109", status="POSITIVE", rationale="positive")
    d=OperationalValidationDecisionBoundary().decide(result, decision_id="d110", status="VALIDATED", rationale="validated")
    assert (d.hypothesis_id,d.audit_id,d.specification_id,d.run_id)==("h104","a106","s107","r108")
    assert d.real_execution_allowed is False

def test_p108_requires_positive_sample():
    a=OperationalHypothesisAuditBoundary().audit(admission(), audit_id="a", rationale="x")
    s=OperationalValidationSpecificationBoundary().specify(a, specification_id="s", test_id="t", environment="LAB", criteria="x")
    with pytest.raises(ValueError): OperationalValidationRunBoundary().record(s, run_id="r", sample_size=0, observation="x")

def test_p110_requires_matching_decision():
    a=OperationalHypothesisAuditBoundary().audit(admission(), audit_id="a", rationale="x")
    s=OperationalValidationSpecificationBoundary().specify(a, specification_id="s", test_id="t", environment="LAB", criteria="x")
    r=OperationalValidationRunBoundary().record(s, run_id="r", sample_size=1, observation="x")
    result=OperationalValidationResultBoundary().conclude(r, result_id="res", status="NEGATIVE", rationale="x")
    with pytest.raises(ValueError): OperationalValidationDecisionBoundary().decide(result, decision_id="d", status="VALIDATED", rationale="x")
