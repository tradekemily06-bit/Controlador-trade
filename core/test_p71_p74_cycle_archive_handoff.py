import pytest

from core.p67_adaptation_cycle import AdaptationCycleBoundary
from core.p68_adaptation_disposition import AdaptationDispositionBoundary, Disposition
from core.p69_cycle_eligibility import Eligibility, NextCycleEligibilityBoundary
from core.p70_adaptation_cycle_closure import AdaptationCycleClosureBoundary
from core.p71_cycle_closure_audit import ClosureAuditStatus, CycleClosureAuditBoundary
from core.p72_cycle_archive import CycleArchiveBoundary
from core.p73_next_cycle_admission import NextCycleAdmissionBoundary
from core.p74_next_cycle_handoff import NextCycleHandoffBoundary


def closure(eligibility=Eligibility.ELIGIBLE):
    cycle = AdaptationCycleBoundary().consolidate(None) if False else None
    # P70 is tested through a minimal valid artifact to keep this block focused.
    from core.p70_adaptation_cycle_closure import AdaptationCycleClosure
    return AdaptationCycleClosure(
        proposal_id="p-74",
        application_id="a-74",
        observation_id="obs-74",
        disposition="RETAIN",
        eligibility=eligibility.value,
        summary="closed",
    )


def test_p71_to_p74_preserve_provenance():
    audited = CycleClosureAuditBoundary().audit(
        closure(), status=ClosureAuditStatus.VERIFIED, rationale="verified"
    )
    archived = CycleArchiveBoundary().archive(audited, archive_id="arch-74")
    admission = NextCycleAdmissionBoundary().admit(archived, rationale="eligible")
    handoff = NextCycleHandoffBoundary().create(
        admission, handoff_id="handoff-74", context="ready for analysis"
    )
    assert handoff.archive_id == "arch-74"
    assert handoff.proposal_id == "p-74"
    assert handoff.application_id == "a-74"
    assert handoff.observation_id == "obs-74"
    assert handoff.real_execution_allowed is False
    with pytest.raises(Exception):
        handoff.context = "changed"


def test_p71_rejects_incomplete_provenance():
    from core.p70_adaptation_cycle_closure import AdaptationCycleClosure
    bad = AdaptationCycleClosure("", "a", "o", "RETAIN", "ELIGIBLE", "closed")
    with pytest.raises(ValueError):
        CycleClosureAuditBoundary().audit(
            bad, status=ClosureAuditStatus.VERIFIED, rationale="verified"
        )


def test_p72_requires_verified_audit():
    audited = CycleClosureAuditBoundary().audit(
        closure(), status=ClosureAuditStatus.BLOCKED, rationale="blocked"
    )
    with pytest.raises(ValueError):
        CycleArchiveBoundary().archive(audited, archive_id="arch-74")


def test_p73_blocks_non_eligible_cycle():
    audited = CycleClosureAuditBoundary().audit(
        closure(Eligibility.REVIEW_REQUIRED),
        status=ClosureAuditStatus.VERIFIED,
        rationale="verified",
    )
    archived = CycleArchiveBoundary().archive(audited, archive_id="arch-review")
    with pytest.raises(ValueError):
        NextCycleAdmissionBoundary().admit(archived, rationale="attempt")


def test_p74_requires_admission_and_context():
    audited = CycleClosureAuditBoundary().audit(
        closure(), status=ClosureAuditStatus.VERIFIED, rationale="verified"
    )
    archived = CycleArchiveBoundary().archive(audited, archive_id="arch-74")
    admission = NextCycleAdmissionBoundary().admit(archived, rationale="eligible")
    with pytest.raises(ValueError):
        NextCycleHandoffBoundary().create(admission, handoff_id="", context="x")
    with pytest.raises(ValueError):
        NextCycleHandoffBoundary().create(admission, handoff_id="h", context="")
