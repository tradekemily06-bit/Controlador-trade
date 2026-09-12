from __future__ import annotations

import secrets
import time
from collections import defaultdict, deque
from dataclasses import dataclass

MAX_BODY_BYTES = 256 * 1024
RATE_LIMIT_REQUESTS = 60
RATE_LIMIT_WINDOW_SECONDS = 60


@dataclass
class _Bucket:
    timestamps: deque[float]


class SecurityGuard:
    """Small dependency-free HTTP safety layer.

    This is deliberately not an authentication provider. Production identity,
    tenant isolation and HTTPS termination belong to the deployment boundary.
    The application remains fail-closed for REAL execution.
    """

    def __init__(self, limit: int = RATE_LIMIT_REQUESTS, window: int = RATE_LIMIT_WINDOW_SECONDS) -> None:
        self.limit = limit
        self.window = window
        self._buckets: dict[str, _Bucket] = defaultdict(lambda: _Bucket(deque()))

    def request_id(self) -> str:
        return secrets.token_hex(16)

    def client_key(self, environ) -> str:
        # Reverse proxies must be configured explicitly before trusting forwarded IPs.
        return str(environ.get("REMOTE_ADDR") or "unknown")[:128]

    def allow(self, environ, now: float | None = None) -> bool:
        current = time.monotonic() if now is None else now
        bucket = self._buckets[self.client_key(environ)]
        cutoff = current - self.window
        while bucket.timestamps and bucket.timestamps[0] <= cutoff:
            bucket.timestamps.popleft()
        if len(bucket.timestamps) >= self.limit:
            return False
        bucket.timestamps.append(current)
        return True

    @staticmethod
    def headers(request_id: str) -> list[tuple[str, str]]:
        return [
            ("X-Request-ID", request_id),
            ("X-Content-Type-Options", "nosniff"),
            ("X-Frame-Options", "DENY"),
            ("Referrer-Policy", "no-referrer"),
            ("Permissions-Policy", "camera=(), microphone=(), geolocation=()"),
            ("Content-Security-Policy", "default-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"),
            ("Cache-Control", "no-store"),
        ]


SECURITY = SecurityGuard()
