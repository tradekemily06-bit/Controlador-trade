import pytest

from core.p85_trusted_knowledge_release import TrustedKnowledgeRelease
from core.p86_knowledge_release_audit import KnowledgeReleaseAuditBoundary, ReleaseAuditStatus
from core.p87_controlled_knowledge_interpretation import ControlledKnowledgeInterpretationBoundary
from core.p88_controlled_use_authorization import ControlledUseAuthorizationBoundary
from core.p89_knowledge_governance_closure import KnowledgeGovernanceClosureBoundary


def release():
    return TrustedKnowledgeRelease("k1", "p1", "d1", "r1", "h1", "statement")


def test_p86_p89_flow_preserves_provenance():
    audit = KnowledgeReleaseAuditBoundary().audit(release(), audit_id="a1", rationale="complete")
    assert audit.status is ReleaseAuditStatus.VERIFIED
    interpretation = ControlledKnowledgeInterpretationBoundary().interpret(audit, interpretation_id="i1", interpretation="controlled")
    authorization = ControlledUseAuthorizationBoundary().authorize(interpretation, authorization_id="u1", scope="lab")
    closure = KnowledgeGovernanceClosureBoundary().close(authorization, closure_id="c1")
    assert closure.knowledge_id == "k1"
    assert closure.hypothesis_id == "h1"
    assert closure.scope == "lab"
    assert closure.real_execution_allowed is False


def test_p87_requires_verified_audit():
    blocked = KnowledgeReleaseAuditBoundary().audit(release(), audit_id="a", rationale="x")
    blocked = type(blocked)(blocked.audit_id, blocked.knowledge_id, blocked.decision_id, blocked.result_id, blocked.hypothesis_id, ReleaseAuditStatus.BLOCKED, blocked.rationale)
    with pytest.raises(ValueError):
        ControlledKnowledgeInterpretationBoundary().interpret(blocked, interpretation_id="i", interpretation="x")


def test_p88_requires_scope():
    audit = KnowledgeReleaseAuditBoundary().audit(release(), audit_id="a", rationale="x")
    interpretation = ControlledKnowledgeInterpretationBoundary().interpret(audit, interpretation_id="i", interpretation="x")
    with pytest.raises(ValueError):
        ControlledUseAuthorizationBoundary().authorize(interpretation, authorization_id="u", scope="")
