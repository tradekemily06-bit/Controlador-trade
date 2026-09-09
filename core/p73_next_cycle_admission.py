from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from core.p72_cycle_archive import CycleArchiveRecord


class AdmissionStatus(str, Enum):
    ADMITTED = "ADMITTED"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class NextCycleAdmission:
    archive_id: str
    proposal_id: str
    application_id: str
    observation_id: str
    status: AdmissionStatus
    rationale: str


class NextCycleAdmissionBoundary:
    def admit(
        self,
        archive: CycleArchiveRecord | None,
        *,
        rationale: str,
    ) -> NextCycleAdmission:
        if not isinstance(archive, CycleArchiveRecord):
            raise ValueError("invalid cycle archive")
        if archive.eligibility != "ELIGIBLE":
            raise ValueError("cycle is not eligible for next-cycle admission")
        if not isinstance(rationale, str) or not rationale.strip():
            raise ValueError("admission rationale is required")
        return NextCycleAdmission(
            archive_id=archive.archive_id,
            proposal_id=archive.proposal_id,
            application_id=archive.application_id,
            observation_id=archive.observation_id,
            status=AdmissionStatus.ADMITTED,
            rationale=rationale.strip(),
        )
