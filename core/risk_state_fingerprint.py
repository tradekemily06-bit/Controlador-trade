from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from datetime import datetime, timezone

from core.operational_state import OperationalState


RISK_STATE_FINGERPRINT_VERSION = 1


def _canonical_value(value: object) -> object:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise ValueError("last_processed_candle must be timezone-aware")
        return value.astimezone(timezone.utc).isoformat()
    return value


def risk_state_identity(state: OperationalState) -> str:
    """Return a deterministic identity for every risk-relevant field.

    Unknown values remain explicit as null; they are never replaced by safe
    defaults. The identity is intentionally broker-agnostic so a future
    authoritative broker/account provider can use the same contract.
    """
    payload = {
        "version": RISK_STATE_FINGERPRINT_VERSION,
        "state": {
            key: _canonical_value(value)
            for key, value in asdict(state).items()
        },
    }
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
