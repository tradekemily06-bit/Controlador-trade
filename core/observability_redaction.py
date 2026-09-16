from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

REDACTED = "[REDACTED]"

_SENSITIVE_KEY_PARTS = (
    "password",
    "passwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "access_key",
    "private_key",
    "credential",
    "authorization",
    "cookie",
    "session",
)


def is_sensitive_key(key: object) -> bool:
    if not isinstance(key, str):
        return False
    normalized = key.strip().lower().replace("-", "_")
    return any(part in normalized for part in _SENSITIVE_KEY_PARTS)


def redact(value: Any) -> Any:
    """Return a safe copy suitable for logs/audit diagnostics.

    This function never mutates caller-owned structures and fails closed for
    sensitive mapping keys. It deliberately preserves ordinary scalar values
    so diagnostics remain useful without exposing credential-bearing fields.
    """
    if isinstance(value, Mapping):
        return {
            key: REDACTED if is_sensitive_key(key) else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, tuple):
        return tuple(redact(item) for item in value)
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, set):
        return {redact(item) for item in value}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [redact(item) for item in value]
    return value


def redact_event(*, event_type: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(event_type, str) or not event_type.strip():
        raise ValueError("event_type is required")
    if not isinstance(payload, Mapping):
        raise ValueError("payload must be a mapping")
    return {"event_type": event_type.strip(), "payload": redact(payload)}
