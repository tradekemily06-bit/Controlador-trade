from __future__ import annotations

from dataclasses import dataclass
from core.p106_operational_hypothesis_audit import OperationalHypothesisAudit

@dataclass(frozen=True)
class OperationalValidationSpecification:
    specification_id: str
    audit_id: str
    hypothesis_id: str
    test_id: str
    environment: str
    criteria: str
    real_execution_allowed: bool = False

class OperationalValidationSpecificationBoundary:
    def specify(self, audit: OperationalHypothesisAudit | None, *, specification_id: str, test_id: str, environment: str, criteria: str) -> OperationalValidationSpecification:
        if not isinstance(audit, OperationalHypothesisAudit) or audit.status != "VERIFIED":
            raise ValueError("P106 audit must be VERIFIED")
        if not all(isinstance(v, str) and v.strip() for v in (specification_id, test_id, environment, criteria)):
            raise ValueError("specification fields are required")
        return OperationalValidationSpecification(specification_id.strip(), audit.audit_id, audit.hypothesis_id, test_id.strip(), environment.strip(), criteria.strip())
