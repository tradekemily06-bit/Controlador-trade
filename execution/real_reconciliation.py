from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


_RECONCILIATION_ISSUER = object()


@dataclass(frozen=True)
class RealReconciliationObservation:
    """Read-only broker observation used to close an uncertain REAL request.

    This object is evidence, not a dispatch command. A production reconciler must
    obtain it by querying the broker/exchange without placing a new order.
    """

    request_id: str
    executed: bool
    external_id: str | None
    observed_at: datetime
    source: str
    _issuer: object = None

    @property
    def issued_by_boundary(self) -> bool:
        return self._issuer is _RECONCILIATION_ISSUER


class RealReconciliationPort(Protocol):
    """Read-only external reconciliation boundary.

    Implementations must query external execution state and never submit orders.
    The REAL gateway never accepts a naked boolean as reconciliation evidence.
    """

    def lookup(self, request_id: str) -> RealReconciliationObservation:
        ...


class RealReconciliationEvidenceBoundary:
    """Issues observations only after a read-only reconciler has obtained them."""

    def __init__(self) -> None:
        # Capabilities are instance-bound: one evidence boundary must not be able
        # to mint observations through another boundary instance.
        self._provider_capability = object()

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
    ) -> RealReconciliationObservation:
        if provider_capability is not self._provider_capability:
            raise ValueError("evidência REAL exige capability do provider somente leitura.")
        return RealReconciliationObservation(
            request_id=request_id,
            executed=executed,
            external_id=external_id,
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
    if (
        not isinstance(observation.observed_at, datetime)
        or observation.observed_at.tzinfo is None
        or observation.observed_at.utcoffset() is None
    ):
        return False
    if not isinstance(observation.source, str) or not observation.source.strip():
        return False
    if observation.executed:
        return isinstance(observation.external_id, str) and bool(observation.external_id.strip())
    return observation.external_id is None
