from __future__ import annotations

from collections.abc import Mapping
from typing import Any


MAX_TRUSTED_IDENTITY_LENGTH = 320


def trusted_identity_from_headers(headers: Any, configured_name: str) -> str:
    """Read a trusted HTTP identity header without depending on header-name casing.

    Conflicting duplicate spellings and malformed matching values fail closed
    rather than selecting an arbitrary identity. Header values are never
    inferred from forwarded client fields.
    """
    if not isinstance(configured_name, str) or not configured_name.strip():
        return ""
    if not isinstance(headers, Mapping):
        return ""
    target = configured_name.strip().casefold()
    matching_values = [
        value
        for key, value in headers.items()
        if isinstance(key, str) and key.strip().casefold() == target
    ]
    if not matching_values or any(
        not isinstance(value, str) or not value.strip()
        for value in matching_values
    ):
        return ""
    values = {value.strip() for value in matching_values}
    if len(values) != 1:
        return ""
    identity = next(iter(values))
    if len(identity) > MAX_TRUSTED_IDENTITY_LENGTH:
        return ""
    if any(ord(character) < 32 or ord(character) == 127 for character in identity):
        return ""
    return identity
