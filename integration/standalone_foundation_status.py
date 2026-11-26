"""Read-only integrity checks for the standalone runtime's SQLite foundation."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


_DATABASES = (
    ("fiscal", "fiscal-reserve.sqlite3", True, {"fiscal_reserve_entries", "fiscal_reserve_settings"}),
    ("ecosystem_state", "ecosystem-state.sqlite3", True, {"ecosystem_state"}),
    ("notification_outbox", "notification-outbox.sqlite3", True, {"notification_outbox"}),
    ("decision_memory", "decision-memory.sqlite3", True, {"decisions"}),
    ("assistant_conversations", "assistant-conversations.sqlite3", True, {"conversations", "messages"}),
    ("market_timeframe_monitor", "market-timeframe-monitor.sqlite3", False, {"market_timeframe_watch", "market_timeframe_results"}),
)


def _integrity(path: Path, expected_tables: set[str]) -> tuple[str, list[str]]:
    # Read-only URI: readiness must never create, migrate, or mutate a database.
    uri = f"{path.resolve().as_uri()}?mode=ro"
    with sqlite3.connect(uri, uri=True, timeout=2) as connection:
        result = connection.execute("PRAGMA quick_check").fetchone()
        if not result or str(result[0]).lower() != "ok":
            return (str(result[0]) if result else "NO_RESULT"), []
        actual_tables = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    missing = sorted(expected_tables - actual_tables)
    return "ok", missing


def standalone_storage_status(runtime: Any) -> dict[str, Any]:
    """Report actual local SQLite presence/integrity without overstating production readiness."""
    runtime_dir = getattr(runtime, "runtime_dir", None)
    if runtime_dir is None:
        return {
            "provider": "LOCAL_SQLITE",
            "required_stores": "NOT_AVAILABLE",
            "stores": [],
            "tenant_isolation": "UNKNOWN",
            "multi_tenant_isolation": "NOT_IMPLEMENTED",
            "backup_restore": "NOT_CONFIGURED",
            "production_storage": "NOT_PROVEN_BY_LOCAL_SQLITE_HEALTH",
            "execution_authorized": False,
        }
    root = Path(runtime_dir)
    stores = []
    required_ready = True
    for store_id, filename, required, expected_tables in _DATABASES:
        path = root / filename
        missing_tables: list[str] = []
        if not path.is_file():
            state = "MISSING"
            detail = None
        else:
            try:
                detail, missing_tables = _integrity(path, expected_tables)
                if detail != "ok":
                    state = "INTEGRITY_ERROR"
                elif missing_tables:
                    state = "SCHEMA_INCOMPLETE"
                else:
                    state = "HEALTHY"
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
            "missing_tables": missing_tables,
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
