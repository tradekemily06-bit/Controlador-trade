"""Read-only integrity checks for the standalone runtime's SQLite foundation."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from urllib.parse import quote
from typing import Any


_DATABASES = (
    ("fiscal", "fiscal-reserve.sqlite3", True),
    ("ecosystem_state", "ecosystem-state.sqlite3", True),
    ("notification_outbox", "notification-outbox.sqlite3", True),
    ("decision_memory", "decision-memory.sqlite3", True),
    ("assistant_conversations", "assistant-conversations.sqlite3", True),
    ("market_timeframe_monitor", "market-timeframe-monitor.sqlite3", False),
)


def _integrity(path: Path) -> str:
    # Read-only URI: readiness must never create, migrate, or mutate a database.
    uri = f"file:{quote(str(path.resolve()))}?mode=ro"
    with sqlite3.connect(uri, uri=True, timeout=2) as connection:
        result = connection.execute("PRAGMA quick_check").fetchone()
    return str(result[0]) if result else "NO_RESULT"


def standalone_storage_status(runtime: Any) -> dict[str, Any]:
    """Report actual local SQLite presence/integrity without overstating production readiness."""
    root = Path(runtime.runtime_dir)
    stores = []
    required_ready = True
    for store_id, filename, required in _DATABASES:
        path = root / filename
        if not path.is_file():
            state = "MISSING"
            detail = None
        else:
            try:
                detail = _integrity(path)
                state = "HEALTHY" if detail == "ok" else "INTEGRITY_ERROR"
            except (OSError, sqlite3.Error) as exc:
                state = "UNREADABLE"
                detail = type(exc).__name__
        if required and state != "HEALTHY":
            required_ready = False
        stores.append({
            "id": store_id,
            "state": state,
            "required": required,
            "integrity": detail,
        })
    return {
        "provider": "LOCAL_SQLITE",
        "required_stores": "HEALTHY" if required_ready else "DEGRADED",
        "stores": stores,
        "tenant_isolation": "SINGLE_CONFIGURED_RUNTIME_IDENTITY",
        "multi_tenant_isolation": "NOT_IMPLEMENTED",
        "backup_restore": "NOT_CONFIGURED",
        "production_storage": "NOT_PROVEN_BY_LOCAL_SQLITE_HEALTH",
        "execution_authorized": False,
    }
