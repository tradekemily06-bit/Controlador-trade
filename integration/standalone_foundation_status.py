"""Read-only integrity checks for the standalone runtime's SQLite foundation."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


_DATABASES = (
    ("fiscal", "fiscal-reserve.sqlite3", True, {
        "fiscal_reserve_entries": {"entry_id", "owner_id", "category", "entry_type", "realized_result_brl", "reserve_rate", "reserve_amount_brl", "reference", "occurred_on", "created_at", "notes"},
        "fiscal_reserve_settings": {"owner_id", "category", "rate", "rate_source"},
        "fiscal_reserve_pending_foreign": {
            "pending_id", "owner_id", "reference", "original_amount", "original_currency",
            "instrument", "jurisdiction", "occurred_on", "status", "created_at",
        },
        "fiscal_pending_reviews": {
            "review_id", "owner_id", "pending_id", "candidate_classification",
            "confirmed_jurisdiction", "reviewer_name", "reviewer_role",
            "professional_registration", "evidence_reference", "reviewed_on", "created_at",
        },
        "fiscal_reserve_pending_domestic": {
            "pending_id", "owner_id", "reference", "instrument", "occurred_on",
            "status", "created_at",
        },
        "fiscal_domestic_pending_reviews": {
            "review_id", "owner_id", "pending_id", "candidate_classification",
            "confirmed_jurisdiction", "reviewer_name", "reviewer_role",
            "professional_registration", "evidence_reference", "reviewed_on", "created_at",
        },
    }),
    ("ecosystem_state", "ecosystem-state.sqlite3", True, {
        "ecosystem_state": {"key", "value_json"},
    }),
    ("tenant_state", "tenant-state.sqlite3", True, {
        "tenant_state": {"tenant_id", "subject_id", "key", "value_json", "updated_at"},
    }),
    ("tenant_market_data", "tenant-connection-timeframe-monitor.sqlite3", True, {
        "tenant_connection_timeframe_watch": {
            "tenant_id", "subject_id", "connection_id", "symbol", "timeframe",
            "enabled", "created_at", "last_processed_candle", "last_signal",
            "last_status", "last_error",
        },
        "tenant_connection_timeframe_results": {
            "tenant_id", "subject_id", "connection_id", "symbol", "timeframe",
            "candle_at", "result_json", "recorded_at",
        },
        "tenant_connection_timeframe_processing_lease": {
            "lease_key", "owner_token", "expires_at",
        },
        "tenant_connection_notification_outbox": {
            "event_id", "tenant_id", "subject_id", "connection_id", "symbol",
            "timeframe", "candle_at", "result_json", "created_at", "attempts",
            "lease_until", "lease_token", "delivered_at", "dead_at", "last_error",
        },
    }),
    ("mt5_relay_tokens", "tenant-mt5-relay-tokens.sqlite3", True, {
        "tenant_mt5_relay_tokens": {
            "token_hash", "tenant_id", "subject_id", "connection_id",
            "source_id", "created_at", "revoked",
        },
    }),
    ("tradingview_webhook_secrets", "tenant-tradingview-webhook-secrets.sqlite3", True, {
        "tenant_tradingview_webhook_secrets": {
            "secret_hash", "tenant_id", "subject_id", "connection_id", "revoked",
        },
    }),
    ("tenant_tradingview_alerts", "tenant-tradingview-alerts.sqlite3", True, {
        "tenant_tradingview_alert_events": {
            "tenant_id", "subject_id", "connection_id", "event_id", "ticker",
            "interval", "action", "price", "fired_at", "received_at", "payload_json",
        },
    }),
    ("ctrader_oauth_state", "tenant-ctrader-oauth-state.sqlite3", False, {
        "tenant_oauth_states": {
            "state_hash", "tenant_id", "subject_id", "connection_id",
            "provider_id", "expires_at", "consumed_at",
        },
    }),
    ("ctrader_oauth_tokens", "tenant-ctrader-oauth-tokens.sqlite3", False, {
        "tenant_oauth_tokens": {
            "tenant_id", "subject_id", "connection_id", "provider_id",
            "key_id", "ciphertext_b64", "expires_at", "scopes_json",
            "updated_at", "revoked_at",
        },
    }),
    ("notification_outbox", "notification-outbox.sqlite3", True, {
        "notification_outbox": {
            "idempotency_key", "payload_json", "status", "attempts",
            "available_at", "lease_until", "lease_token", "created_at",
            "delivered_at", "last_error",
        },
    }),
    ("decision_memory", "decision-memory.sqlite3", True, {
        "decisions": {"decision_id", "created_at", "symbol", "timeframe", "signal", "score", "confirmed", "reason", "execution_allowed", "outcome", "outcome_source"},
    }),
    ("assistant_conversations", "assistant-conversations.sqlite3", True, {
        "conversations": {"id", "owner", "title", "updated_at"},
        "messages": {"id", "conversation_id", "role", "content", "created_at"},
    }),
    ("market_timeframe_monitor", "market-timeframe-monitor.sqlite3", False, {
        "market_timeframe_watch_v2": {"tenant_id", "subject_id", "symbol", "timeframe", "enabled", "created_at", "last_processed_candle", "last_signal", "last_status", "last_error"},
        "market_timeframe_results_v2": {"tenant_id", "subject_id", "symbol", "timeframe", "candle_at", "result_json", "recorded_at"},
    }),
)


def _integrity(path: Path, expected_schema: dict[str, set[str]]) -> tuple[str, dict[str, list[str]]]:
    # Read-only URI: readiness must never create, migrate, or mutate a database.
    uri = f"{path.resolve().as_uri()}?mode=ro"
    with sqlite3.connect(uri, uri=True, timeout=2) as connection:
        result = connection.execute("PRAGMA quick_check").fetchone()
        if not result or str(result[0]).lower() != "ok":
            return (str(result[0]) if result else "NO_RESULT"), {}
        foreign_key_violations = connection.execute("PRAGMA foreign_key_check").fetchall()
        if foreign_key_violations:
            return f"FOREIGN_KEY_VIOLATIONS:{len(foreign_key_violations)}", {}
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


def _backup_status(runtime: Any) -> dict[str, Any]:
    if getattr(runtime, "runtime_dir", None) is None:
        return {"state": "NOT_AVAILABLE", "scheduler": None}
    scheduler = getattr(runtime, "backup_scheduler", None)
    if scheduler is None:
        return {"state": "ON_DEMAND_LOCAL_ONLY", "scheduler": None}
    try:
        status = scheduler.status()
    except Exception as exc:
        return {"state": "STATUS_UNAVAILABLE", "scheduler": None, "error_class": type(exc).__name__}
    return {
        "state": "SCHEDULED_LOCAL_ONLY",
        "scheduler": status,
    }


def standalone_storage_status(runtime: Any) -> dict[str, Any]:
    """Report actual local SQLite presence/integrity without overstating production readiness."""
    runtime_dir = getattr(runtime, "runtime_dir", None)
    backup = _backup_status(runtime)
    if runtime_dir is None:
        return {
            "provider": "LOCAL_SQLITE",
            "required_stores": "NOT_AVAILABLE",
            "stores": [],
            "tenant_isolation": "UNKNOWN",
            "multi_tenant_isolation": "NOT_IMPLEMENTED",
            "backup_restore": backup["state"],
            "backup_scheduler": backup["scheduler"],
            "production_storage": "NOT_PROVEN_BY_LOCAL_SQLITE_HEALTH",
            "deployment_topology": "UNKNOWN_NO_RUNTIME_DIRECTORY",
            "multi_replica_readiness": "BLOCKED_RUNTIME_NOT_AVAILABLE",
            "production_release_blockers": [
                "RUNTIME_STORAGE_NOT_AVAILABLE",
                "POSTGRESQL_OR_EQUIVALENT_SHARED_TRANSACTIONAL_DATABASE",
                "DISTRIBUTED_PROCESSING_AND_OUTBOX_LEASES",
                "DURABLE_SHARED_OAUTH_STORAGE_WITH_KMS",
                "EXTERNAL_NOTIFICATION_DELIVERY_PROVIDER",
                "TRUSTED_IDENTITY_PROVIDER_RUNTIME_VERIFICATION",
                "BACKUP_RESTORE_AND_RECOVERY_VALIDATION",
            ],
            "execution_authorized": False,
        }
    root = Path(runtime_dir)
    stores = []
    required_ready = True
    for store_id, filename, required, expected_schema in _DATABASES:
        path = root / filename
        missing_schema: dict[str, list[str]] = {}
        if path.is_symlink():
            # A database path must remain inside the configured runtime directory.
            # Following a symlink here could make readiness inspect an unrelated file.
            state = "UNSAFE_PATH"
            detail = "SYMLINK_NOT_ALLOWED"
        elif not path.is_file():
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
        "backup_restore": backup["state"],
        "backup_scheduler": backup["scheduler"],
        "production_storage": "NOT_PROVEN_BY_LOCAL_SQLITE_HEALTH",
        "deployment_topology": "SINGLE_HOST_ONLY",
        "multi_replica_readiness": "BLOCKED_SHARED_TRANSACTIONAL_DATABASE_REQUIRED",
        "production_release_blockers": [
            "POSTGRESQL_OR_EQUIVALENT_SHARED_TRANSACTIONAL_DATABASE",
            "DISTRIBUTED_PROCESSING_AND_OUTBOX_LEASES",
            "DURABLE_SHARED_OAUTH_STORAGE_WITH_KMS",
            "EXTERNAL_NOTIFICATION_DELIVERY_PROVIDER",
            "TRUSTED_IDENTITY_PROVIDER_RUNTIME_VERIFICATION",
            "BACKUP_RESTORE_AND_RECOVERY_VALIDATION",
        ],
        "execution_authorized": False,
    }
