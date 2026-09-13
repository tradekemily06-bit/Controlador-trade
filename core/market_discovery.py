from __future__ import annotations

from dataclasses import fields
from typing import Any

from .general_market_observation import GeneralMarketObservation


_METADATA_FIELDS = {"candle_count", "directions", "observations"}


def _scalar_relationship(name: str, value: Any) -> str | None:
    if isinstance(value, bool):
        return f"{name.upper()}={str(value).lower()}"
    if isinstance(value, str):
        return f"{name.upper()}={value}"
    return None


def discover_market_relationships(
    observation: GeneralMarketObservation | None,
) -> tuple[str, ...]:
    """Discover neutral relationships from available observations.

    This layer is intentionally open-ended: it derives relationship signatures
    from the observation object's fields instead of maintaining a closed list
    of named market patterns. Discovery never becomes a trade decision.
    """
    if observation is None:
        return ()

    values = {
        field.name: getattr(observation, field.name)
        for field in fields(observation)
        if field.name not in _METADATA_FIELDS
    }

    relationships: list[str] = []
    for name, value in values.items():
        relationship = _scalar_relationship(name, value)
        if relationship is not None:
            relationships.append(relationship)

    for name, value in values.items():
        if not name.endswith("_change") or not isinstance(value, str):
            continue
        base_name = name[: -len("_change")]
        if value != "UNDEFINED":
            relationships.append(f"{base_name.upper()}_DIRECTION={value}")

    categorical = [item for item in relationships if "=" in item]
    for index, left in enumerate(categorical):
        for right in categorical[index + 1 :]:
            relationships.append(f"COMBINATION[{left}|{right}]")

    return tuple(dict.fromkeys(relationships))
