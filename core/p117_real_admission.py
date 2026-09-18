from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import weakref

from core.p112_real_execution_contract import RealExecutionAuthorization
from core.p116_real_release_audit import RealReleaseAudit, _is_boundary_verified_audit


class RealAdmissionStatus(str, Enum):
    ADMITTED = "ADMITTED"
    BLOCKED = "BLOCKED"


class _AdmissionProvenanceToken:
    """Private identity token proving issuance by RealAdmissionBoundary."""


@dataclass(frozen=True)
class RealAdmission:
    """Immutable admission bound to the exact operation, audit and authorization."""

    admission_id: str
    audit_id: str
    status: RealAdmissionStatus
    broker_id: str
    adapter_id: str
    request_id: str
    symbol: str
    reasons: tuple[str, ...]
    _provenance_token: _AdmissionProvenanceToken | None = field(default=None, repr=False, compare=False)
    _authorization_ref: weakref.ReferenceType[RealExecutionAuthorization] | None = field(
        default=None, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        for name in ("admission_id", "audit_id", "broker_id", "adapter_id", "request_id", "symbol"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} é obrigatório.")
        if not isinstance(self.status, RealAdmissionStatus):
            raise TypeError("status de admissão REAL inválido.")
        if not isinstance(self.reasons, tuple) or not all(isinstance(reason, str) for reason in self.reasons):
            raise TypeError("reasons da admissão REAL deve ser uma tupla de strings.")
        if self._provenance_token is not None and not isinstance(self._provenance_token, _AdmissionProvenanceToken):
            raise TypeError("proveniência da admissão REAL inválida.")
        if self._authorization_ref is not None and not isinstance(
            self._authorization_ref, weakref.ReferenceType
        ):
            raise TypeError("referência da autorização REAL inválida.")

    @property
    def admitted(self) -> bool:
        if self.status is not RealAdmissionStatus.ADMITTED:
            return False
        token = self._provenance_token
        if token is None:
            return False
        reference = _ADMITTED_PROVENANCE.get(id(token))
        if reference is None or reference() is not token:
            return False
        authorization_ref = self._authorization_ref
        authorization = authorization_ref() if authorization_ref is not None else None
        return authorization is not None and authorization.active


_ADMITTED_PROVENANCE: dict[int, weakref.ReferenceType[_AdmissionProvenanceToken]] = {}


def _is_boundary_admitted(admission: object) -> bool:
    if not isinstance(admission, RealAdmission) or not admission.admitted:
        return False
    token = admission._provenance_token
    if token is None:
        return False
    reference = _ADMITTED_PROVENANCE.get(id(token))
    return reference is not None and reference() is token


class RealAdmissionBoundary:
    def admit(
        self,
        *,
        admission_id: str,
        audit_id: str,
        audit_verified: RealReleaseAudit,
        authorization_active: RealExecutionAuthorization,
        safety_ready: bool,
        broker_available: bool,
        broker_id: str,
        adapter_id: str,
        request_id: str,
        symbol: str,
    ) -> RealAdmission:
        for name, value in (
            ("admission_id", admission_id), ("audit_id", audit_id),
            ("broker_id", broker_id), ("adapter_id", adapter_id),
            ("request_id", request_id), ("symbol", symbol),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} é obrigatório.")

        if not isinstance(audit_verified, RealReleaseAudit) or not _is_boundary_verified_audit(audit_verified):
            raise ValueError("auditoria P116 VERIFIED emitida pela fronteira é obrigatória para admissão REAL.")
        if audit_verified.audit_id != audit_id:
            raise ValueError("audit_id não corresponde à auditoria P116.")
        if not isinstance(authorization_active, RealExecutionAuthorization) or not authorization_active.active:
            raise ValueError("autorização REAL ativa emitida pela fronteira é obrigatória para admissão REAL.")
        if authorization_active.audit_id != audit_id:
            raise ValueError("auditoria da autorização REAL difere da admissão.")
        if authorization_active.broker_id.strip().lower() != broker_id.strip().lower():
            raise ValueError("broker da autorização REAL difere da admissão.")
        if authorization_active.adapter_id.strip() != adapter_id.strip():
            raise ValueError("adapter_id da autorização REAL difere da admissão.")
        if authorization_active.request_id.strip() != request_id.strip():
            raise ValueError("request_id da autorização REAL difere da admissão.")
        if authorization_active.symbol.strip().upper() != symbol.strip().upper():
            raise ValueError("símbolo da autorização REAL difere da admissão.")

        for name, value in (("safety_ready", safety_ready), ("broker_available", broker_available)):
            if not isinstance(value, bool):
                raise TypeError(f"{name} deve ser booleano.")

        reasons = []
        if not safety_ready:
            reasons.append("segurança REAL não pronta")
        if not broker_available:
            reasons.append("corretora indisponível")
        status = RealAdmissionStatus.ADMITTED if not reasons else RealAdmissionStatus.BLOCKED
        token = _AdmissionProvenanceToken() if status is RealAdmissionStatus.ADMITTED else None
        authorization_ref = weakref.ref(authorization_active) if token is not None else None
        admission = RealAdmission(
            admission_id, audit_id, status, broker_id, adapter_id,
            request_id, symbol, tuple(reasons), token, authorization_ref,
        )
        if token is not None:
            key = id(token)
            _ADMITTED_PROVENANCE[key] = weakref.ref(
                token,
                lambda _reference, key=key: _ADMITTED_PROVENANCE.pop(key, None),
            )
        return admission
