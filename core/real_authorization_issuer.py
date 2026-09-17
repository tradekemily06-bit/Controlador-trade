from __future__ import annotations

from core.p112_real_execution_contract import RealExecutionAuthorization
from core.p116_real_release_audit import RealReleaseAudit


class RealAuthorizationIssuer:
    """Factory for the established REAL authorization contract.

    This layer does not itself enable REAL. It requires a VERIFIED P116 audit
    and explicit approval before constructing the already-established contract.
    The actual dispatch path remains responsible for authoritative safety,
    identity, admission and barrier checks.
    """

    def issue(
        self,
        *,
        audit: RealReleaseAudit,
        authorization_id: str,
        audit_id: str,
        broker_id: str,
        adapter_id: str,
        request_id: str,
        symbol: str,
        explicit_approval: bool,
    ) -> RealExecutionAuthorization:
        if not isinstance(audit, RealReleaseAudit) or not audit.verified:
            raise ValueError("auditoria P116 VERIFIED é obrigatória para emitir autorização REAL.")
        if audit.audit_id != audit_id:
            raise ValueError("audit_id não corresponde à auditoria P116.")
        if explicit_approval is not True:
            raise ValueError("aprovação explícita é obrigatória para emitir autorização REAL.")
        return RealExecutionAuthorization(
            authorization_id, audit_id, broker_id, adapter_id, request_id, symbol,
            True, True,
        )
