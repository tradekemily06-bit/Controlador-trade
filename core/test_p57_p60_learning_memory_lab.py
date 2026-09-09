import pytest

from core.p54_learning_validation import LearningValidationBoundary, ValidationStatus
from core.p55_trusted_knowledge import TrustedKnowledgeBoundary
from core.p57_knowledge_memory import KnowledgeMemoryBoundary
from core.p58_memory_audit import MemoryAuditBoundary, MemoryAuditStatus
from core.p59_knowledge_lab import KnowledgeLabBoundary
from core.p60_adaptation_proposal import AdaptationProposalBoundary
from core.p53_learning_hypothesis import LearningHypothesisBoundary
from core.p52_learning_evidence import LearningEvidence


def knowledge():
    evidence = LearningEvidence("cycle-57", "WIN", 9.0)
    hypothesis = LearningHypothesisBoundary().propose(evidence, hypothesis_id="h-57", statement="testable condition")
    validation = LearningValidationBoundary().validate(
        hypothesis, test_id="t-57", status=ValidationStatus.VALIDATED,
        sample_size=20, observation="explicit observation"
    )
    return TrustedKnowledgeBoundary().promote(validation, knowledge_id="k-57", statement="validated knowledge")


def test_p57_records_traceable_immutable_memory():
    result = KnowledgeMemoryBoundary().record(knowledge(), memory_id="m-57")
    assert result.knowledge_id == "k-57"
    assert result.hypothesis_id == "h-57"
    assert result.test_id == "t-57"
    with pytest.raises(Exception):
        result.memory_id = "other"


def test_p58_audits_provenance_before_lab():
    record = KnowledgeMemoryBoundary().record(knowledge(), memory_id="m-58")
    decision = MemoryAuditBoundary().audit(record)
    assert decision.status is MemoryAuditStatus.AUDITABLE
    assert decision.memory_id == record.memory_id
    with pytest.raises(ValueError):
        MemoryAuditBoundary().audit(None)


def test_p59_requires_auditable_memory_and_is_immutable():
    record = KnowledgeMemoryBoundary().record(knowledge(), memory_id="m-59")
    audit = MemoryAuditBoundary().audit(record)
    run = KnowledgeLabBoundary().run(audit, record, lab_id="lab-59", scenario="replay scenario")
    assert run.hypothesis_id == "h-57"
    with pytest.raises(ValueError):
        KnowledgeLabBoundary().run(None, record, lab_id="lab-59", scenario="replay")
    with pytest.raises(Exception):
        run.lab_id = "other"


def test_p60_creates_proposal_without_applying_it_or_enabling_real_execution():
    record = KnowledgeMemoryBoundary().record(knowledge(), memory_id="m-60")
    audit = MemoryAuditBoundary().audit(record)
    run = KnowledgeLabBoundary().run(audit, record, lab_id="lab-60", scenario="controlled scenario")
    proposal = AdaptationProposalBoundary().propose(run, proposal_id="proposal-60", rationale="lab result requires review")
    assert proposal.applied is False
    assert proposal.real_execution_allowed is False
    assert proposal.memory_id == "m-60"
    with pytest.raises(Exception):
        proposal.applied = True
