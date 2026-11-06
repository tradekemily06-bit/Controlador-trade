from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def trusted_identity_from_headers(headers: Any, configured_name: str) -> str:
    """Read a trusted HTTP identity header without depending on header-name casing.

    Conflicting duplicate spellings fail closed rather than selecting an arbitrary
    identity value. Header values are never inferred from forwarded client fields.
    """
    if not isinstance(configured_name, str) or not configured_name.strip():
        return ""
    if not isinstance(headers, Mapping):
        return ""
    target = configured_name.strip().casefold()
    values = {
        str(value).strip()
        for key, value in headers.items()
        if isinstance(key, str)
        and key.strip().casefold() == target
        and isinstance(value, str)
        and value.strip()
    }
    return next(iter(values)) if len(values) == 1 else ""
