import pytest

from core.p74_next_cycle_handoff import NextCycleHandoff
from core.p75_handoff_validation import HandoffValidationBoundary, HandoffValidationStatus
from core.p76_cycle_context import NextCycleContextBoundary
from core.p77_context_audit import ContextAuditBoundary, ContextAuditStatus
from core.p78_hypothesis_preparation import HypothesisPreparationBoundary
from core.p79_validation_admission import ValidationAdmissionBoundary


def handoff():
    return NextCycleHandoff("h", "a", "p", "app", "o", "context")


def test_p75_to_p79_preserve_boundary_and_provenance():
    validation = HandoffValidationBoundary().validate(
        handoff(), status=HandoffValidationStatus.VERIFIED, rationale="verified"
    )
    context = NextCycleContextBoundary().create(
        validation, context_id="ctx", context="descriptive context"
    )
    audit = ContextAuditBoundary().audit(
        context, status=ContextAuditStatus.AUDITABLE, rationale="complete"
    )
    hypothesis = HypothesisPreparationBoundary().prepare(
        audit, hypothesis_id="hyp", statement="testable statement"
    )
    admission = ValidationAdmissionBoundary().admit(hypothesis, admission_id="adm")
    assert admission.hypothesis_id == "hyp"
    assert admission.context_id == "ctx"
    assert admission.handoff_id == "h"
    assert admission.validated is not True
    assert admission.real_execution_allowed is False
    with pytest.raises(Exception):
        admission.status = "BLOCKED"


def test_p75_blocks_incomplete_handoff():
    with pytest.raises(ValueError):
        HandoffValidationBoundary().validate(
            NextCycleHandoff("", "a", "p", "app", "o", "context"),
            status=HandoffValidationStatus.VERIFIED,
            rationale="verified",
        )


def test_p76_requires_verified_handoff():
    validation = HandoffValidationBoundary().validate(
        handoff(), status=HandoffValidationStatus.BLOCKED, rationale="blocked"
    )
    with pytest.raises(ValueError):
        NextCycleContextBoundary().create(validation, context_id="ctx", context="x")


def test_p77_requires_complete_context():
    context = NextCycleContextBoundary().create(
        HandoffValidationBoundary().validate(
            handoff(), status=HandoffValidationStatus.VERIFIED, rationale="verified"
        ),
        context_id="ctx", context="x"
    )
    with pytest.raises(ValueError):
        ContextAuditBoundary().audit(context, status=ContextAuditStatus.BLOCKED, rationale="")


def test_p78_requires_auditable_context():
    context = NextCycleContextBoundary().create(
        HandoffValidationBoundary().validate(
            handoff(), status=HandoffValidationStatus.VERIFIED, rationale="verified"
        ), context_id="ctx", context="x"
    )
    audit = ContextAuditBoundary().audit(
        context, status=ContextAuditStatus.BLOCKED, rationale="blocked"
    )
    with pytest.raises(ValueError):
        HypothesisPreparationBoundary().prepare(audit, hypothesis_id="hyp", statement="x")


def test_p79_requires_unvalidated_hypothesis():
    from core.p78_hypothesis_preparation import PreparedHypothesis
    with pytest.raises(ValueError):
        ValidationAdmissionBoundary().admit(
            PreparedHypothesis("h", "c", "x", "statement", validated=True),
            admission_id="a",
        )
