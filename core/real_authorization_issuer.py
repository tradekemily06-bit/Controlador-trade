from __future__ import annotations

from core.p112_real_execution_contract import RealExecutionAuthorization
from core.p116_real_release_audit import RealReleaseAudit, _is_boundary_verified_audit


class RealAuthorizationIssuer:
    """Factory for the established REAL authorization contract.

    This layer does not itself enable REAL. It requires a VERIFIED P116 audit
    issued by the release-audit boundary, plus explicit approval, before it can
    construct the already-established contract. Directly fabricating a
    ``RealReleaseAudit(..., VERIFIED, ...)`` object is intentionally rejected.

    The provenance check is an in-process code-level control. It is not a
    cryptographic identity system and does not authenticate an external human;
    future release governance must provide that higher-level authority.
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
        if not _is_boundary_verified_audit(audit) or not audit.verified:
            raise ValueError("auditoria P116 VERIFIED emitida pela fronteira é obrigatória para emitir autorização REAL.")
        if audit.audit_id != audit_id:
            raise ValueError("audit_id não corresponde à auditoria P116.")
        if explicit_approval is not True:
            raise ValueError("aprovação explícita é obrigatória para emitir autorização REAL.")
        return RealExecutionAuthorization(
            authorization_id, audit_id, broker_id, adapter_id, request_id, symbol,
            True, True,
        )
