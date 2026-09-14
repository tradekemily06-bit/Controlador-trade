from __future__ import annotations

from collections.abc import Iterable
from typing import Any


def prevalidate_replay_cases(cases: Iterable[Any]) -> list[dict[str, Any]]:
    """Validate every replay case before any analysis side effect.

    Replay has no artificial scenario-count ceiling. The HTTP/security layer
    may protect transport resources, but the replay domain itself must not
    silently truncate or reject a legitimate analysis because of an arbitrary
    case count. Validation is complete before persistence begins so malformed
    input can never create a partial replay history.
    """
    accepted: list[dict[str, Any]] = []
    for index, payload in enumerate(cases, start=1):
        if not isinstance(payload, dict):
            raise ValueError(f"cada cenário deve ser um objeto (posição {index})")
        accepted.append(payload)
    return accepted
