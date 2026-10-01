from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class RealManualConfirmation:
    """Proof that a human explicitly confirmed one exact REAL request."""

    confirmation_id: str
    request_id: str
    request_fingerprint: str
    created_at: datetime
    expires_at: datetime
