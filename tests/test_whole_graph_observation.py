from __future__ import annotations

import pytest

from core.whole_graph_observation import (
    WholeGraphObservationBoundary,
    WholeGraphStatus,
)


def test_complete_context_requires_every_available_node_accounted_for() -> None:
    result = WholeGraphObservationBoundary().audit(
        context_id="cycle-1",
        available_nodes=("history", "present", "structure", "liquidity"),
        observed_nodes=("history", "present", "structure", "liquidity"),
        relationships_reviewed=("history->present", "structure->liquidity"),
    )

    assert result.status is WholeGraphStatus.COMPLETE
    assert result.complete is True
    assert result.gaps == ()


def test_missing_provider_data_is_explicitly_preserved_as_a_gap() -> None:
    result = WholeGraphObservationBoundary().audit(
        context_id="cycle-2",
        available_nodes=("history", "present", "volume"),
        observed_nodes=("history", "present"),
        gaps={"volume": "provider did not supply volume for this cycle"},
    )

    assert result.status is WholeGraphStatus.PARTIAL
    assert result.complete is False
    assert result.gaps[0].node_id == "volume"


def test_unaccounted_available_node_fails_closed() -> None:
    with pytest.raises(ValueError, match="every available node"):
        WholeGraphObservationBoundary().audit(
            context_id="cycle-3",
            available_nodes=("history", "present", "structure"),
            observed_nodes=("history", "present"),
        )


def test_observing_unknown_node_fails_closed() -> None:
    with pytest.raises(ValueError, match="subset"):
        WholeGraphObservationBoundary().audit(
            context_id="cycle-4",
            available_nodes=("history", "present"),
            observed_nodes=("history", "future"),
        )


def test_empty_context_is_insufficient_not_complete() -> None:
    result = WholeGraphObservationBoundary().audit(
        context_id="cycle-5",
        available_nodes=(),
        observed_nodes=(),
    )

    assert result.status is WholeGraphStatus.INSUFFICIENT
    assert result.complete is False
