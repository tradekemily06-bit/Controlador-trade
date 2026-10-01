from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256

from execution.ports import ExecutionRequest
from datetime import datetime


@dataclass(frozen=True)
class RealManualConfirmation:
    """Proof that a human explicitly confirmed one exact REAL request."""

    confirmation_id: str
    request_id: str
    request_fingerprint: str
    created_at: datetime
    expires_at: datetime


def request_fingerprint(request: ExecutionRequest) -> str:
    canonical = "|".join(
        (
            request.symbol.strip(),
            request.signal.value,
            f"{float(request.amount):.12g}",
            str(request.duration_seconds),
            request.mode.value,
            str(request.request_id or "").strip(),
        )
    )
    return sha256(canonical.encode("utf-8")).hexdigest()
