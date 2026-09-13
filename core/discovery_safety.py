from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DiscoverySafety:
    """Safety classification for newly discovered market relationships."""

    relationships: tuple[str, ...]
    status: str
    execution_authorized: bool = False


def assess_discovery_safety(
    relationships: tuple[str, ...] | list[str] | None,
) -> DiscoverySafety:
    """Keep discovery strictly observational until validated elsewhere."""
    normalized = tuple(dict.fromkeys(relationships or ()))
    if not normalized:
        return DiscoverySafety(relationships=(), status="NO_DISCOVERY")
    return DiscoverySafety(
        relationships=normalized,
        status="OBSERVATION_ONLY",
        execution_authorized=False,
    )


def is_operationally_admitted(*, tests_passed: bool, explicitly_admitted: bool) -> bool:
    """Return whether a discovered relationship passed both required gates.

    A discovery cannot become operational from detection alone. The ecosystem
    must first pass its validation tests and a decision layer must explicitly
    admit the relationship. Either condition being false keeps it out of the
    operational path.
    """
    return bool(tests_passed and explicitly_admitted)
