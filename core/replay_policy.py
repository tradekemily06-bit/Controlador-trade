from __future__ import annotations

from collections.abc import Iterable
from typing import Any


MAX_REPLAY_CASES = 50


def prevalidate_replay_cases(cases: Iterable[Any]) -> list[dict[str, Any]]:
    """Validate the complete replay envelope before any analysis side effect.

    The iterable is consumed only through the allowed limit plus one sentinel
    item. This prevents processing/persisting the first 50 scenarios and only
    discovering a 51st scenario afterwards.
    """
    accepted: list[dict[str, Any]] = []
    for index, payload in enumerate(cases, start=1):
        if index > MAX_REPLAY_CASES:
            raise ValueError(f"replay aceita no máximo {MAX_REPLAY_CASES} cenários")
        if not isinstance(payload, dict):
            raise ValueError(f"cada cenário deve ser um objeto (posição {index})")
        accepted.append(payload)
    return accepted
