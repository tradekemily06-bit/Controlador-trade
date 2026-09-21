from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from enum import Enum


class ReconciliationOutcome(str, Enum):
    """Semantic result of an external read-side reconciliation query."""

    EXECUTED = "EXECUTED"
    NOT_EXECUTED = "NOT_EXECUTED"
    NOT_FOUND = "NOT_FOUND"
    NOT_VISIBLE_YET = "NOT_VISIBLE_YET"
    QUERY_FAILED = "QUERY_FAILED"
    AMBIGUOUS = "AMBIGUOUS"


class ExternalIdentityKind(str, Enum):
    """Identifies which broker-side object an external_id names."""

    ORDER = "ORDER"
    DEAL = "DEAL"
    POSITION = "POSITION"
    EXECUTION = "EXECUTION"
    UNKNOWN = "UNKNOWN"


class _ObservationIssuer:
    __slots__ = ()


_RECONCILIATION_ISSUER = _ObservationIssuer()


@dataclass(frozen=True)
class RealReconciliationObservation:
    """Read-only broker observation used to close an uncertain REAL request."""

    request_id: str
    executed: bool
    external_id: str | None
    outcome: ReconciliationOutcome | None = None
    external_id_kind: ExternalIdentityKind = ExternalIdentityKind.UNKNOWN
    provider: str | None = None
    account_id: str | None = None
    symbol: str | None = None
    side: str | None = None
    amount: float | None = None
    correlation: str | None = None
    observed_at: datetime
    source: str
    _issuer: object = None

    @property
    @property
    def effective_outcome(self) -> ReconciliationOutcome:
        # Backward-compatible observations issued by the internal boundary are
        # explicitly classified. New providers should always pass outcome.
        return self.outcome or (
            ReconciliationOutcome.EXECUTED if self.executed else ReconciliationOutcome.NOT_EXECUTED
        )

    def issued_by_boundary(self) -> bool:
        return self._issuer is _RECONCILIATION_ISSUER


class RealReconciliationPort(Protocol):
    """Read-only external reconciliation boundary."""

    def lookup(self, request_id: str) -> RealReconciliationObservation:
        ...


class RealReconciliationEvidenceBoundary:
    """Issues observations only after a read-only reconciler has obtained them."""

    def __init__(self, *, capability: object | None = None) -> None:
        if capability is not _RECONCILIATION_ISSUER:
            raise ValueError("emissor de evidência REAL não pode ser criado por código externo.")
        self._provider_capability = object()

    @classmethod
    def _internal(cls) -> "RealReconciliationEvidenceBoundary":
        return cls(capability=_RECONCILIATION_ISSUER)

    @property
    def provider_capability(self) -> object:
        return self._provider_capability

    def issue(
        self,
        *,
        request_id: str,
        executed: bool,
        external_id: str | None,
        observed_at: datetime,
        source: str,
        provider_capability: object,
        outcome: ReconciliationOutcome | None = None,
        external_id_kind: ExternalIdentityKind = ExternalIdentityKind.UNKNOWN,
        provider: str | None = None,
        account_id: str | None = None,
        symbol: str | None = None,
        side: str | None = None,
        amount: float | None = None,
        correlation: str | None = None,
    ) -> RealReconciliationObservation:
        if provider_capability is not self._provider_capability:
            raise ValueError("evidência REAL exige capability do provider somente leitura.")
        return RealReconciliationObservation(
            request_id=request_id,
            executed=executed,
            external_id=external_id,
            outcome=outcome,
            external_id_kind=external_id_kind,
            provider=provider,
            account_id=account_id,
            symbol=symbol,
            side=side,
            amount=amount,
            correlation=correlation,
            observed_at=observed_at,
            source=source,
            _issuer=_RECONCILIATION_ISSUER,
        )


def validate_observation(
    request_id: str,
    observation: RealReconciliationObservation,
) -> bool:
    """Fail closed on malformed or contradictory reconciliation evidence."""
    if type(observation) is not RealReconciliationObservation or not observation.issued_by_boundary:
        return False
    if observation.request_id != request_id:
        return False
    if not isinstance(observation.executed, bool):
        return False
    if observation.outcome is not None and not isinstance(observation.outcome, ReconciliationOutcome):
        return False
    outcome = observation.effective_outcome
    if outcome is ReconciliationOutcome.EXECUTED and not observation.executed:
        return False
    if outcome is not ReconciliationOutcome.EXECUTED and observation.executed:
        return False
    if (
        not isinstance(observation.observed_at, datetime)
        or observation.observed_at.tzinfo is None
        or observation.observed_at.utcoffset() is None
    ):
        return False
    if not isinstance(observation.source, str) or not observation.source.strip():
        return False
    if observation.executed:
        if not isinstance(observation.external_id, str) or not observation.external_id.strip():
            return False
        if observation.external_id_kind is ExternalIdentityKind.UNKNOWN:
            return False
        return outcome is ReconciliationOutcome.EXECUTED
    # A negative terminal result must be definitive. NOT_FOUND, delayed
    # visibility, query failure and ambiguity are deliberately non-terminal.
    if observation.external_id is not None:
        return False
    return outcome in (
        ReconciliationOutcome.NOT_EXECUTED,
        ReconciliationOutcome.NOT_FOUND,
        ReconciliationOutcome.NOT_VISIBLE_YET,
        ReconciliationOutcome.QUERY_FAILED,
        ReconciliationOutcome.AMBIGUOUS,
    )
