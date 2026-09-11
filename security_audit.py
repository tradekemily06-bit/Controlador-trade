from __future__ import annotations

import hashlib
import secrets
import time
from collections import deque
from dataclasses import asdict, dataclass

MAX_SECURITY_EVENTS = 1000


@dataclass(frozen=True)
class SecurityEvent:
    timestamp: float
    request_id: str
    method: str
    path: str
    status: int
    client_hash: str


class SecurityAudit:
    """Bounded, privacy-conscious security event trail.

    Stores no raw IP, credentials, authorization tokens or request bodies.
    Persistent centralized audit storage belongs to the production boundary.
    """

    def __init__(self, max_events: int = MAX_SECURITY_EVENTS) -> None:
        self.max_events = max_events
        self._salt = secrets.token_bytes(32)
        self._events: deque[SecurityEvent] = deque(maxlen=max_events)

    def record(self, *, request_id: str, method: str, path: str, status: int, client_key: str) -> None:
        digest = hashlib.sha256(self._salt + client_key.encode("utf-8", "replace")).hexdigest()
        self._events.append(SecurityEvent(time.time(), request_id, method, path[:512], int(status), digest))

    def snapshot(self) -> list[dict[str, object]]:
        return [asdict(event) for event in self._events]


AUDIT = SecurityAudit()
