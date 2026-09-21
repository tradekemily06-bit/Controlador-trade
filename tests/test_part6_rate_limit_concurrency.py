from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from security_guard import SecurityGuard


def test_rate_limit_is_atomic_under_concurrent_requests():
    guard = SecurityGuard(limit=1, window=60)
    environ = {"REMOTE_ADDR": "client-a"}

    with ThreadPoolExecutor(max_workers=16) as pool:
        results = list(pool.map(lambda _: guard.allow(environ, now=1000.0), range(64)))

    assert sum(results) == 1
