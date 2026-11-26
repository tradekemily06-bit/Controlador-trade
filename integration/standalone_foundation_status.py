"""Read-only integrity checks for the standalone runtime's SQLite foundation."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


_DATABASES = (
    ("fiscal", "fiscal-reserve.sqlite3", True, {
        "fiscal_reserve_entries": {"entry_id", "owner_id", "category", "entry_type", "realized_result_brl", "reserve_rate", "reserve_amount_brl", "reference", "occurred_on", "created_at", "notes"},
        "fiscal_reserve_settings": {"owner_id", "category", "rate", "rate_source"},
    }),
    ("ecosystem_state", "ecosystem-state.sqlite3", True, {
        "ecosystem_state": {"key", "value_json"},
    }),
    ("tenant_state", "tenant-state.sqlite3", True, {
        "tenant_state": {"tenant_id", "key", "value_json", "updated_at"},
    }),
    ("notification_outbox", "notification-outbox.sqlite3", True, {
        "notification_outbox": {"idempotency_key", "payload_json", "status", "attempts", "available_at", "lease_until", "created_at", "delivered_at", "last_error"},
    }),
    ("decision_memory", "decision-memory.sqlite3", True, {
        "decisions": {"decision_id", "created_at", "symbol", "timeframe", "signal", "score", "confirmed", "reason", "execution_allowed", "outcome", "outcome_source"},
    }),
    ("assistant_conversations", "assistant-conversations.sqlite3", True, {
        "conversations": {"id", "owner", "title", "updated_at"},
        "messages": {"id", "conversation_id", "role", "content", "created_at"},
    }),
    ("market_timeframe_monitor", "market-timeframe-monitor.sqlite3", False, {
        "market_timeframe_watch": {"symbol", "timeframe", "enabled", "created_at", "last_processed_candle", "last_signal", "last_status", "last_error"},
        "market_timeframe_results": {"symbol", "timeframe", "candle_at", "result_json", "recorded_at"},
    }),
)


def _integrity(path: Path, expected_schema: dict[str, set[str]]) -> tuple[str, dict[str, list[str]]]:
    # Read-only URI: readiness must never create, migrate, or mutate a database.
    uri = f"{path.resolve().as_uri()}?mode=ro"
    with sqlite3.connect(uri, uri=True, timeout=2) as connection:
        result = connection.execute("PRAGMA quick_check").fetchone()
        if not result or str(result[0]).lower() != "ok":
            return (str(result[0]) if result else "NO_RESULT"), {}
        missing: dict[str, list[str]] = {}
        for table, expected_columns in expected_schema.items():
            exists = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                (table,),
            ).fetchone()
            if not exists:
                missing[table] = ["<table>"]
                continue
            actual_columns = {
                str(row[1])
                for row in connection.execute(f'PRAGMA table_info("{table}")').fetchall()
            }
            absent = sorted(expected_columns - actual_columns)
            if absent:
                missing[table] = absent
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
    for store_id, filename, required, expected_schema in _DATABASES:
        path = root / filename
        missing_schema: dict[str, list[str]] = {}
        if not path.is_file():
            state = "MISSING"
            detail = None
        else:
            try:
                detail, missing_schema = _integrity(path, expected_schema)
                if detail != "ok":
                    state = "INTEGRITY_ERROR"
                elif missing_schema:
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
            "missing_schema": missing_schema,
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
