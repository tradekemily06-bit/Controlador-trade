from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import weakref


class RealAdmissionStatus(str, Enum):
    ADMITTED = "ADMITTED"
    BLOCKED = "BLOCKED"


class _AdmissionProvenanceToken:
    """Private identity token proving issuance by RealAdmissionBoundary."""


@dataclass(frozen=True)
class RealAdmission:
    """Immutable admission bound to the exact operation and adapter."""

    admission_id: str
    audit_id: str
    status: RealAdmissionStatus
    broker_id: str
    adapter_id: str
    request_id: str
    symbol: str
    reasons: tuple[str, ...]
    _provenance_token: _AdmissionProvenanceToken | None = field(default=None, repr=False, compare=False)

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

    @property
    def admitted(self) -> bool:
        if self.status is not RealAdmissionStatus.ADMITTED:
            return False
        token = self._provenance_token
        if token is None:
            return False
        reference = _ADMITTED_PROVENANCE.get(id(token))
        return reference is not None and reference() is token


# Admission is a gate, not merely a data shape. The execution gateway must
# distinguish a boundary-issued admission from a field-identical fabricated
# dataclass. The private token is held by the exact object and separately
# registered by identity, without retaining admissions forever.
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
    def admit(self, *, admission_id: str, audit_id: str, audit_verified: bool,
              authorization_active: bool, safety_ready: bool,
              broker_available: bool, broker_id: str, adapter_id: str,
              request_id: str, symbol: str) -> RealAdmission:
        for name, value in (
            ("admission_id", admission_id), ("audit_id", audit_id),
            ("broker_id", broker_id), ("adapter_id", adapter_id),
            ("request_id", request_id), ("symbol", symbol),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} é obrigatório.")

        for name, value in (
            ("audit_verified", audit_verified),
            ("authorization_active", authorization_active),
            ("safety_ready", safety_ready),
            ("broker_available", broker_available),
        ):
            if not isinstance(value, bool):
                raise TypeError(f"{name} deve ser booleano.")

        reasons = []
        for ok, label in (
            (audit_verified, "auditoria P116 não verificada"),
            (authorization_active, "autorização REAL não ativa"),
            (safety_ready, "segurança REAL não pronta"),
            (broker_available, "corretora indisponível"),
        ):
            if not ok:
                reasons.append(label)
        status = RealAdmissionStatus.ADMITTED if not reasons else RealAdmissionStatus.BLOCKED
        token = _AdmissionProvenanceToken() if status is RealAdmissionStatus.ADMITTED else None
        admission = RealAdmission(
            admission_id, audit_id, status, broker_id, adapter_id,
            request_id, symbol, tuple(reasons), token,
        )
        if token is not None:
            key = id(token)
            _ADMITTED_PROVENANCE[key] = weakref.ref(
                token,
                lambda _reference, key=key: _ADMITTED_PROVENANCE.pop(key, None),
            )
        return admission
