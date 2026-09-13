from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DiscoverySafety:
    """Safety classification for newly discovered market relationships.

    Discovery is informational only. A discovered relationship can never
    authorize a trade, score, risk decision, or execution by itself.
    """

    relationships: tuple[str, ...]
    status: str
    execution_authorized: bool = False


def assess_discovery_safety(
    relationships: tuple[str, ...] | list[str] | None,
) -> DiscoverySafety:
    normalized = tuple(dict.fromkeys(relationships or ()))
    if not normalized:
        return DiscoverySafety(relationships=(), status="NO_DISCOVERY")
    return DiscoverySafety(
        relationships=normalized,
        status="OBSERVATION_ONLY",
        execution_authorized=False,
    )
