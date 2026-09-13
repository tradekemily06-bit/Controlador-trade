"""Whole-context observation boundary for contextual market reasoning."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Mapping


class WholeGraphStatus(str, Enum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    INSUFFICIENT = "INSUFFICIENT"


@dataclass(frozen=True)
class ObservationGap:
    node_id: str
    reason: str


@dataclass(frozen=True)
class WholeGraphObservation:
    context_id: str
    available_node_ids: tuple[str, ...]
    observed_node_ids: tuple[str, ...]
    gaps: tuple[ObservationGap, ...]
    relationships_reviewed: tuple[str, ...]
    status: WholeGraphStatus
    complete: bool


class WholeGraphObservationBoundary:
    """Audit whether every materially available context node was accounted for.

    The available set is supplied by the upstream context builder, so this
    boundary stays open-ended instead of becoming a closed catalogue of
    market facts. Missing information must be explicit rather than silently
    ignored or invented.
    """

    def audit(
        self,
        *,
        context_id: str,
        available_nodes: Iterable[str],
        observed_nodes: Iterable[str],
        gaps: Mapping[str, str] | None = None,
        relationships_reviewed: Iterable[str] = (),
    ) -> WholeGraphObservation:
        if not isinstance(context_id, str) or not context_id.strip():
            raise ValueError("context_id is required")

        available = self._normalize_ids(available_nodes, "available_nodes")
        observed = self._normalize_ids(observed_nodes, "observed_nodes")
        relationships = self._normalize_ids(
            relationships_reviewed, "relationships_reviewed"
        )
        available_set = set(available)
        observed_set = set(observed)
        if observed_set - available_set:
            raise ValueError("observed_nodes must be a subset of available_nodes")

        raw_gaps = gaps or {}
        if not isinstance(raw_gaps, Mapping):
            raise ValueError("gaps must be a mapping")

        normalized_gaps: list[ObservationGap] = []
        for node_id, reason in raw_gaps.items():
            if node_id not in available_set:
                raise ValueError("gap node must be declared available")
            if node_id in observed_set:
                raise ValueError("an observed node cannot also be a gap")
            if not isinstance(reason, str) or not reason.strip():
                raise ValueError("every observation gap requires a reason")
            normalized_gaps.append(ObservationGap(node_id, reason.strip()))

        missing = available_set - observed_set - {
            gap.node_id for gap in normalized_gaps
        }
        if missing:
            raise ValueError(
                "every available node must be observed or have an explicit gap"
            )

        if not available:
            status = WholeGraphStatus.INSUFFICIENT
        elif normalized_gaps:
            status = WholeGraphStatus.PARTIAL
        else:
            status = WholeGraphStatus.COMPLETE

        return WholeGraphObservation(
            context_id=context_id.strip(),
            available_node_ids=available,
            observed_node_ids=observed,
            gaps=tuple(normalized_gaps),
            relationships_reviewed=relationships,
            status=status,
            complete=status is WholeGraphStatus.COMPLETE,
        )

    @staticmethod
    def _normalize_ids(values: Iterable[str], field_name: str) -> tuple[str, ...]:
        result: list[str] = []
        for value in values:
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must contain non-empty strings")
            value = value.strip()
            if value not in result:
                result.append(value)
        return tuple(result)
