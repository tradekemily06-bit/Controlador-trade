from __future__ import annotations

from core.p112_real_execution_contract import RealExecutionAuthorization, _ISSUER_CAPABILITY
from core.p116_real_release_audit import RealReleaseAudit


class RealAuthorizationIssuer:
    """Single controlled issuer for an active REAL authorization.

    Construction of an authorization object alone is never sufficient to make
    it active. The issuer requires a verified P116 release audit and an
    explicit approval at the issuance boundary. No broker or execution call is
    performed here.
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
            authorization_id=authorization_id,
            audit_id=audit_id,
            broker_id=broker_id,
            adapter_id=adapter_id,
            request_id=request_id,
            symbol=symbol,
            explicitly_enabled=True,
            real_execution_allowed=True,
            _issuer_capability=_ISSUER_CAPABILITY,
        )
