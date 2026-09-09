from __future__ import annotations

import pytest

from core.p99_operational_feedback_closure import OperationalFeedbackClosure
from core.p100_operational_feedback_audit import OperationalFeedbackAudit, OperationalFeedbackAuditBoundary
from core.p101_operational_feedback_archive import OperationalFeedbackArchiveBoundary
from core.p102_next_operational_cycle_readiness import NextOperationalCycleReadinessBoundary
from core.p103_next_operational_cycle_context import NextOperationalCycleContextBoundary
from core.p104_operational_hypothesis_preparation import OperationalHypothesisPreparationBoundary
from core.p105_operational_hypothesis_admission import OperationalHypothesisAdmissionBoundary


def closed_p99() -> OperationalFeedbackClosure:
    return OperationalFeedbackClosure(
        closure_id="c99", disposition_id="d98", assessment_id="a97", observation_id="o96",
        operational_closure_id="c95", admission_id="ad94", evaluation_id="e92",
        use_id="u90", knowledge_id="k85", hypothesis_id="h79", disposition="RETAIN",
    )


def test_p100_to_p105_preserve_provenance_and_block_real_execution():
    audit = OperationalFeedbackAuditBoundary().audit(closed_p99(), audit_id="a100", rationale="verified")
    archive = OperationalFeedbackArchiveBoundary().archive(audit, archive_id="ar101")
    readiness = NextOperationalCycleReadinessBoundary().assess(archive, readiness_id="r102")
    context = NextOperationalCycleContextBoundary().create(readiness, context_id="ctx103", context="controlled context")
    hypothesis = OperationalHypothesisPreparationBoundary().prepare(context, hypothesis_id="h104", statement="testable statement")
    admission = OperationalHypothesisAdmissionBoundary().admit(hypothesis, admission_id="ad105")

    assert admission.hypothesis_id == "h104"
    assert admission.context_id == "ctx103"
    assert admission.readiness_id == "r102"
    assert hypothesis.validated is False
    assert audit.real_execution_allowed is False
    assert archive.real_execution_allowed is False
    assert readiness.real_execution_allowed is False
    assert context.real_execution_allowed is False
    assert hypothesis.real_execution_allowed is False
    assert admission.real_execution_allowed is False


def test_p100_requires_closed_p99():
    open_closure = closed_p99().__class__(**{**closed_p99().__dict__, "status": "OPEN"})
    with pytest.raises(ValueError):
        OperationalFeedbackAuditBoundary().audit(open_closure, audit_id="a", rationale="x")


def test_p101_requires_verified_audit():
    blocked = OperationalFeedbackAudit("a", "c", "ad", "d", "as", "o", "BLOCKED", "x")
    with pytest.raises(ValueError):
        OperationalFeedbackArchiveBoundary().archive(blocked, archive_id="ar")


def test_p104_is_not_validated_and_p105_rejects_validated_hypothesis():
    audit = OperationalFeedbackAuditBoundary().audit(closed_p99(), audit_id="a", rationale="x")
    archive = OperationalFeedbackArchiveBoundary().archive(audit, archive_id="ar")
    readiness = NextOperationalCycleReadinessBoundary().assess(archive, readiness_id="r")
    context = NextOperationalCycleContextBoundary().create(readiness, context_id="ctx", context="x")
    hypothesis = OperationalHypothesisPreparationBoundary().prepare(context, hypothesis_id="h", statement="x")
    assert hypothesis.validated is False
    validated = hypothesis.__class__(**{**hypothesis.__dict__, "validated": True})
    with pytest.raises(ValueError):
        OperationalHypothesisAdmissionBoundary().admit(validated, admission_id="ad")
