from __future__ import annotations

import ipaddress
import hmac
import os
import secrets
import time
import threading
from collections import defaultdict, deque
from dataclasses import dataclass

MAX_BODY_BYTES = 256 * 1024
RATE_LIMIT_REQUESTS = 60
RATE_LIMIT_WINDOW_SECONDS = 60
MAX_TRACKED_CLIENTS = 10_000


@dataclass
class _Bucket:
    timestamps: deque[float]


class SecurityGuard:
    """Small dependency-free HTTP safety layer."""

    def __init__(self, limit: int = RATE_LIMIT_REQUESTS, window: int = RATE_LIMIT_WINDOW_SECONDS) -> None:
        if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
            raise ValueError("limit must be a positive integer")
        if not isinstance(window, int) or isinstance(window, bool) or window < 1:
            raise ValueError("window must be a positive integer")
        self.limit = limit
        self.window = window
        self._buckets: dict[str, _Bucket] = defaultdict(lambda: _Bucket(deque()))
        self._rate_lock = threading.RLock()

    def request_id(self) -> str:
        return secrets.token_hex(16)

    def script_nonce(self) -> str:
        return secrets.token_urlsafe(24)

    def _is_loopback(self, environ) -> bool:
        raw = str(environ.get("REMOTE_ADDR") or "").strip()
        # Unit-test WSGI environments commonly omit REMOTE_ADDR. The real
        # wsgiref server always supplies the peer address; treat an omitted
        # address as local only for this in-process/default-local boundary.
        if not raw:
            return True
        try:
            return ipaddress.ip_address(raw).is_loopback
        except ValueError:
            return raw.lower() == "localhost"

    def requires_remote_auth(self, environ) -> bool:
        if os.environ.get("CONTROLADOR_REQUIRE_API_TOKEN", "").strip().lower() in {"1", "true", "yes"}:
            return True
        # A reverse proxy may make every peer appear as loopback. Treat common
        # forwarding headers as an explicit signal that this is no longer a
        # direct local-client boundary; token auth then becomes mandatory.
        if environ.get("HTTP_FORWARDED") or environ.get("HTTP_X_FORWARDED_FOR") or environ.get("HTTP_X_FORWARDED_HOST"):
            return True
        return not self._is_loopback(environ)

    def authorize(self, environ) -> bool:
        if not self.requires_remote_auth(environ):
            return True
        expected = os.environ.get("CONTROLADOR_API_TOKEN", "").strip()
        if not expected:
            return False
        provided = str(environ.get("HTTP_AUTHORIZATION", ""))
        if not provided.startswith("Bearer "):
            return False
        token = provided[7:].strip()
        return bool(token) and hmac.compare_digest(token, expected)

    def client_key(self, environ) -> str:
        return str(environ.get("REMOTE_ADDR") or "local")[:128]

    def _prune(self, cutoff: float) -> None:
        stale = [
            key
            for key, bucket in self._buckets.items()
            if not bucket.timestamps or bucket.timestamps[-1] <= cutoff
        ]
        for key in stale:
            self._buckets.pop(key, None)

    def _bound_clients(self) -> None:
        while len(self._buckets) > MAX_TRACKED_CLIENTS:
            self._buckets.pop(next(iter(self._buckets)))

    def allow(self, environ, now: float | None = None) -> bool:
        current = time.monotonic() if now is None else now
        cutoff = current - self.window
        with self._rate_lock:
            self._prune(cutoff)
            key = self.client_key(environ)
            bucket = self._buckets[key]
            while bucket.timestamps and bucket.timestamps[0] <= cutoff:
                bucket.timestamps.popleft()
            if len(bucket.timestamps) >= self.limit:
                return False
            bucket.timestamps.append(current)
            self._bound_clients()
            return True

    @staticmethod
    def headers(request_id: str, script_nonce: str | None = None) -> list[tuple[str, str]]:
        script_policy = "'self'" if not script_nonce else f"'self' 'nonce-{script_nonce}'"
        return [
            ("X-Request-ID", request_id),
            ("X-Content-Type-Options", "nosniff"),
            ("X-Frame-Options", "DENY"),
            ("Referrer-Policy", "no-referrer"),
            ("Permissions-Policy", "camera=(), microphone=(), geolocation=()"),
            ("Content-Security-Policy", f"default-src 'self'; script-src {script_policy}; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"),
            ("Cache-Control", "no-store"),
        ]


SECURITY = SecurityGuard()
