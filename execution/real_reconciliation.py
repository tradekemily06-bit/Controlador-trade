from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


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


class RealReconciliationPort(Protocol):
    """Read-only external reconciliation boundary.

    Implementations must query external execution state and never submit orders.
    The REAL gateway never accepts a naked boolean as reconciliation evidence.
    """

    def lookup(self, request_id: str) -> RealReconciliationObservation:
        ...


def validate_observation(
    request_id: str,
    observation: RealReconciliationObservation,
) -> bool:
    """Fail closed on malformed or contradictory reconciliation evidence."""
    if not isinstance(observation, RealReconciliationObservation):
        return False
    if observation.request_id != request_id:
        return False
    if not isinstance(observation.executed, bool):
        return False
    if not isinstance(observation.observed_at, datetime):
        return False
    if not isinstance(observation.source, str) or not observation.source.strip():
        return False
    if observation.executed:
        return isinstance(observation.external_id, str) and bool(observation.external_id.strip())
    return observation.external_id is None
