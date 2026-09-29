from __future__ import annotations

from datetime import datetime

from execution.external_outcome_port import ExternalCloseResult
from core.p49_outcome_reconciliation import ExternalOutcomeObservation
from execution.icmarkets_mt5_demo_outcome import ICMarketsMT5DemoOutcomeBridge


class MT5ExternalOutcomeAdapter:
    """Maps the MT5-specific outcome bridge into the broker-neutral outcome port."""

    def __init__(self, bridge: ICMarketsMT5DemoOutcomeBridge) -> None:
        self._bridge = bridge

    def close_and_observe(self, request_id: str) -> ExternalCloseResult:
        result = self._bridge.close_and_observe(request_id)
        observation = result.outcome_evidence.as_observation() if result.outcome_evidence else None
        return ExternalCloseResult(
            request_id=result.request_id,
            external_container_id=result.external_container_id,
            external_close_id=result.external_close_id,
            closed=result.position_closed,
            observation=observation,
            message=result.message,
        )

    def observe_closed_position(self, request_id: str) -> ExternalOutcomeObservation | None:
        evidence = self._bridge.observe_closed_position(request_id)
        return evidence.as_observation() if evidence is not None else None
