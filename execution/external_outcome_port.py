from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from core.p49_outcome_reconciliation import ExternalOutcomeObservation


@dataclass(frozen=True)
class ExternalCloseResult:
    """Broker-neutral close status returned by an external close adapter."""

    request_id: str
    external_container_id: str | None
    external_close_id: str | None
    closed: bool
    observation: ExternalOutcomeObservation | None
    message: str


class ExternalOutcomeObserver(Protocol):
    """Read-only contract for factual external result observation.

    This capability is deliberately separate from closing. REAL integrations can
    receive verified broker facts through this contract without being granted a
    generic position-close mutation.
    """

    def observe_closed_position(self, request_id: str) -> ExternalOutcomeObservation | None:
        ...


class ExternalClosePort(Protocol):
    """Mutation contract for a controlled external close operation."""

    def close_and_observe(self, request_id: str) -> ExternalCloseResult:
        ...


class ExternalOutcomePort(ExternalClosePort, ExternalOutcomeObserver, Protocol):
    """Backward-compatible combined close + observation contract.

    DEMO adapters may implement both capabilities. A future REAL integration
    may expose only ExternalOutcomeObserver until its own explicit close
    authorization boundary is wired. No broker/platform/transport is encoded
    here.
    """
