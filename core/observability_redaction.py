from __future__ import annotations

import re
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
)

_TEXT_PATTERNS = (
    re.compile(r"(?i)(bearer\\s+)[A-Za-z0-9._~+/=-]+"),
    re.compile(r"(?i)((?:authorization|api[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret)\\s*[=:]\\s*)[^\\s,;]+"),
    re.compile(r"(?i)((?:password|passwd|secret)\\s*[=:]\\s*)[^\\s,;]+"),
    re.compile(r'''(?i)([\\\"']?(?:authorization|api[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret|password|passwd|secret|token|cookie)[\\\"']?\\s*:\\s*[\\\"'])[^\\\"']*([\\\"'])'''),
    re.compile(r"(?i)([?&](?:authorization|api[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret|password|passwd|secret|token|cookie)=)[^&#\\s]+"),
)


def is_sensitive_key(key: object) -> bool:
    if not isinstance(key, str):
        return False
    normalized = key.strip().lower().replace("-", "_")
    return any(part in normalized for part in _SENSITIVE_KEY_PARTS)


def redact_text(value: object) -> str:
    """Redact common credential-bearing patterns from free-form diagnostics."""
    text = str(value)
    for pattern in _TEXT_PATTERNS:
        if pattern.groups == 2:
            text = pattern.sub(lambda match: match.group(1) + REDACTED + match.group(2), text)
        else:
            text = pattern.sub(lambda match: match.group(1) + REDACTED, text)
    return text


def redact(value: Any) -> Any:
    """Return a safe copy suitable for logs/audit diagnostics.

    Caller-owned structures are never mutated. Sensitive mapping keys are
    replaced entirely, nested containers are traversed, free-form strings are
    scanned for common credential-bearing patterns, byte payloads are removed,
    and exception objects are reduced to their type name so their message or
    repr cannot cross the observability boundary.
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
    if isinstance(value, (bytes, bytearray)):
        return REDACTED
    if isinstance(value, BaseException):
        return type(value).__name__
    if isinstance(value, str):
        return redact_text(value)
    return value


def redact_event(*, event_type: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(event_type, str) or not event_type.strip():
        raise ValueError("event_type is required")
    if not isinstance(payload, Mapping):
        raise ValueError("payload must be a mapping")
    return {"event_type": event_type.strip(), "payload": redact(payload)}
