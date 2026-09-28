from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from core.p49_outcome_reconciliation import ExternalOutcomeObservation


@dataclass(frozen=True)
class ExternalCloseResult:
    """Broker-neutral close status returned by an external outcome adapter."""

    request_id: str
    external_container_id: str | None
    external_close_id: str | None
    closed: bool
    observation: ExternalOutcomeObservation | None
    message: str


class ExternalOutcomePort(Protocol):
    """Contract for any broker/platform adapter that can close and observe an operation.

    The ecosystem depends only on this contract. A concrete adapter may use MT5,
    cTrader, a broker REST API, FIX, a terminal bridge, or another transport.
    """

    def close_and_observe(self, request_id: str) -> ExternalCloseResult:
        ...

    def observe_closed_position(self, request_id: str) -> ExternalOutcomeObservation | None:
        ...
