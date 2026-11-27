from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from threading import RLock
from typing import Any

from security.tenant_context import TenantContext
from security.tenant_storage import TenantStorageBoundary, require_tenant_context


class SQLiteTenantStorage(TenantStorageBoundary):
    """SQLite key/value storage scoped to both tenant and authenticated subject.

    This implementation provides durable local persistence and logical
    tenant/user separation inside one database. It is deliberately NOT marked
    production_durable: SQLite on one runtime does not provide the
    multi-instance, backup, identity-provider, or operational guarantees
    required for production SaaS.
    """
    production_durable = False
    _MAX_KEY_LENGTH = 200

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.execute("PRAGMA busy_timeout = 10000")
        return connection

    def _initialize(self) -> None:
        with self._lock, self._connect() as connection:
            existing = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='tenant_state'"
            ).fetchone()
            if existing:
                info = connection.execute('PRAGMA table_info("tenant_state")').fetchall()
                columns = {str(row[1]) for row in info}
                primary_key = [str(row[1]) for row in sorted(info, key=lambda row: row[5]) if row[5]]
                if columns != {"tenant_id", "subject_id", "key", "value_json", "updated_at"} or primary_key != ["tenant_id", "subject_id", "key"]:
                    legacy_exists = connection.execute(
                        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='tenant_state_legacy_unscoped'"
                    ).fetchone()
                    if legacy_exists:
                        raise RuntimeError("legacy tenant state exists; refusing to overwrite unscoped data")
                    connection.execute("DROP INDEX IF EXISTS idx_tenant_state_updated")
                    connection.execute(
                        "ALTER TABLE tenant_state RENAME TO tenant_state_legacy_unscoped"
                    )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS tenant_state (
                    tenant_id TEXT NOT NULL,
                    subject_id TEXT NOT NULL,
                    key TEXT NOT NULL,
                    value_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (tenant_id, subject_id, key)
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_tenant_state_updated "
                "ON tenant_state(tenant_id, subject_id, updated_at)"
            )

    @classmethod
    def _scope(cls, context: TenantContext | None, key: str) -> tuple[str, str, str]:
        trusted = require_tenant_context(context)
        if not isinstance(trusted, TenantContext):
            raise PermissionError("valid trusted tenant context is required")
        if not isinstance(key, str):
            raise ValueError("key must be a string")
        normalized_key = key.strip()
        if not normalized_key or len(normalized_key) > cls._MAX_KEY_LENGTH:
            raise ValueError("key must contain 1 to 200 characters")
        return trusted.tenant_id, trusted.subject_id, normalized_key

    def get(self, context: TenantContext, key: str) -> Any | None:
        tenant_id, subject_id, normalized_key = self._scope(context, key)
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT value_json FROM tenant_state WHERE tenant_id=? AND subject_id=? AND key=?",
                (tenant_id, subject_id, normalized_key),
            ).fetchone()
        return None if row is None else json.loads(row[0])

    def put(self, context: TenantContext, key: str, value: Any) -> None:
        tenant_id, subject_id, normalized_key = self._scope(context, key)
        encoded = json.dumps(
            value, ensure_ascii=False, separators=(",", ":"), allow_nan=False
        )
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO tenant_state(tenant_id, subject_id, key, value_json)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(tenant_id, subject_id, key) DO UPDATE SET
                    value_json=excluded.value_json,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (tenant_id, subject_id, normalized_key, encoded),
            )

    def append_unique_list_item(
        self,
        context: TenantContext,
        key: str,
        item: dict[str, Any],
        *,
        unique_field: str,
        limit: int,
    ) -> bool:
        """Atomically append one unique object within a tenant-scoped list."""
        tenant_id, subject_id, normalized_key = self._scope(context, key)
        if not isinstance(item, dict):
            raise ValueError("item must be an object")
        if not isinstance(unique_field, str) or not unique_field.strip():
            raise ValueError("unique_field is required")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 2000:
            raise ValueError("limit must be an integer between 1 and 2000")
        unique_value = item.get(unique_field)
        if not isinstance(unique_value, str) or not unique_value.strip():
            raise ValueError(f"{unique_field} must be a non-empty string")
        encoded_item = json.dumps(
            item, ensure_ascii=False, separators=(",", ":"), allow_nan=False
        )
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT value_json FROM tenant_state WHERE tenant_id=? AND subject_id=? AND key=?",
                (tenant_id, subject_id, normalized_key),
            ).fetchone()
            current = [] if row is None else json.loads(row[0])
            if not isinstance(current, list) or any(not isinstance(entry, dict) for entry in current):
                raise ValueError("stored tenant list has an invalid shape")
            if any(entry.get(unique_field) == unique_value for entry in current):
                connection.rollback()
                return False
            current.append(json.loads(encoded_item))
            encoded_list = json.dumps(
                current[-limit:], ensure_ascii=False, separators=(",", ":"), allow_nan=False
            )
            connection.execute(
                """
                INSERT INTO tenant_state(tenant_id, subject_id, key, value_json)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(tenant_id, subject_id, key) DO UPDATE SET
                    value_json=excluded.value_json,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (tenant_id, subject_id, normalized_key, encoded_list),
            )
            connection.commit()
        return True


    def put_if_absent_with_index(
        self,
        context: TenantContext,
        record_key: str,
        record_value: Any,
        index_key: str,
        index_item: dict[str, Any],
        *,
        unique_field: str,
        limit: int,
    ) -> bool:
        """Atomically create a record and append its index entry exactly once."""
        tenant_id, subject_id, normalized_record_key = self._scope(context, record_key)
        _, _, normalized_index_key = self._scope(context, index_key)
        if normalized_record_key == normalized_index_key:
            raise ValueError("record and index keys must be different")
        if not isinstance(index_item, dict):
            raise ValueError("index_item must be an object")
        if not isinstance(unique_field, str) or not unique_field.strip():
            raise ValueError("unique_field is required")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 2000:
            raise ValueError("limit must be an integer between 1 and 2000")
        unique_value = index_item.get(unique_field)
        if not isinstance(unique_value, str) or not unique_value.strip():
            raise ValueError(f"{unique_field} must be a non-empty string")
        encoded_record = json.dumps(
            record_value, ensure_ascii=False, separators=(",", ":"), allow_nan=False
        )
        encoded_item = json.dumps(
            index_item, ensure_ascii=False, separators=(",", ":"), allow_nan=False
        )
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT 1 FROM tenant_state WHERE tenant_id=? AND subject_id=? AND key=?",
                (tenant_id, subject_id, normalized_record_key),
            ).fetchone()
            if existing:
                connection.rollback()
                return False
            row = connection.execute(
                "SELECT value_json FROM tenant_state WHERE tenant_id=? AND subject_id=? AND key=?",
                (tenant_id, subject_id, normalized_index_key),
            ).fetchone()
            current = [] if row is None else json.loads(row[0])
            if not isinstance(current, list) or any(not isinstance(entry, dict) for entry in current):
                raise ValueError("stored tenant list has an invalid shape")
            if any(entry.get(unique_field) == unique_value for entry in current):
                raise ValueError("decision index already contains an unbacked record")
            current.append(json.loads(encoded_item))
            encoded_index = json.dumps(
                current[-limit:], ensure_ascii=False, separators=(",", ":"), allow_nan=False
            )
            connection.execute(
                "INSERT INTO tenant_state(tenant_id, subject_id, key, value_json) VALUES (?, ?, ?, ?)",
                (tenant_id, subject_id, normalized_record_key, encoded_record),
            )
            connection.execute(
                """
                INSERT INTO tenant_state(tenant_id, subject_id, key, value_json)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(tenant_id, subject_id, key) DO UPDATE SET
                    value_json=excluded.value_json,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (tenant_id, subject_id, normalized_index_key, encoded_index),
            )
            connection.commit()
        return True

    def upsert_unique_list_item(
        self, context: TenantContext, key: str, item: dict[str, Any],
        *, unique_fields: tuple[str, ...], limit: int,
    ) -> dict[str, Any]:
        """Atomically insert or replace one list item identified by stable fields."""
        tenant_id, subject_id, normalized_key = self._scope(context, key)
        if not isinstance(item, dict) or not unique_fields:
            raise ValueError("item and unique_fields are required")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 200:
            raise ValueError("limit must be an integer between 1 and 200")
        identity = tuple(item.get(field) for field in unique_fields)
        if any(not isinstance(value, str) or not value for value in identity):
            raise ValueError("unique fields must be non-empty strings")
        encoded_item = json.dumps(item, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT value_json FROM tenant_state WHERE tenant_id=? AND subject_id=? AND key=?",
                (tenant_id, subject_id, normalized_key),
            ).fetchone()
            current = [] if row is None else json.loads(row[0])
            if not isinstance(current, list) or any(not isinstance(entry, dict) for entry in current):
                raise ValueError("stored tenant list has an invalid shape")
            match = next((entry for entry in current if all(entry.get(field) == value for field, value in zip(unique_fields, identity))), None)
            if match is not None:
                stable_connection_id = match.get("connection_id")
                match.update(json.loads(encoded_item))
                if stable_connection_id is not None:
                    match["connection_id"] = stable_connection_id
                result = dict(match)
            else:
                if len(current) >= limit:
                    raise ValueError("tenant list limit reached")
                current.append(json.loads(encoded_item))
                result = dict(current[-1])
            encoded = json.dumps(current, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
            connection.execute(
                """INSERT INTO tenant_state(tenant_id, subject_id, key, value_json)
                VALUES (?, ?, ?, ?) ON CONFLICT(tenant_id, subject_id, key)
                DO UPDATE SET value_json=excluded.value_json, updated_at=CURRENT_TIMESTAMP""",
                (tenant_id, subject_id, normalized_key, encoded),
            )
            connection.commit()
        return result

    def update_list_item(
        self, context: TenantContext, key: str, *, match_field: str,
        match_value: str, updates: dict[str, Any],
    ) -> bool:
        """Atomically update one tenant-owned list item without lost writes."""
        tenant_id, subject_id, normalized_key = self._scope(context, key)
        if not isinstance(match_field, str) or not match_field or not isinstance(match_value, str):
            raise ValueError("match field and value are required")
        if not isinstance(updates, dict) or not updates:
            raise ValueError("updates are required")
        encoded_updates = json.dumps(updates, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT value_json FROM tenant_state WHERE tenant_id=? AND subject_id=? AND key=?",
                (tenant_id, subject_id, normalized_key),
            ).fetchone()
            current = [] if row is None else json.loads(row[0])
            if not isinstance(current, list) or any(not isinstance(entry, dict) for entry in current):
                raise ValueError("stored tenant list has an invalid shape")
            target = next((entry for entry in current if entry.get(match_field) == match_value), None)
            if target is None:
                connection.rollback()
                return False
            target.update(json.loads(encoded_updates))
            encoded = json.dumps(current, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
            connection.execute(
                """UPDATE tenant_state SET value_json=?, updated_at=CURRENT_TIMESTAMP
                WHERE tenant_id=? AND subject_id=? AND key=?""",
                (encoded, tenant_id, subject_id, normalized_key),
            )
            connection.commit()
        return True

    def update_list_item_unique(
        self, context: TenantContext, key: str, *, match_field: str,
        match_value: str, updates: dict[str, Any], unique_fields: tuple[str, ...],
    ) -> bool:
        """Atomically update one list item while enforcing tenant-local uniqueness."""
        tenant_id, subject_id, normalized_key = self._scope(context, key)
        if not isinstance(match_field, str) or not match_field or not isinstance(match_value, str):
            raise ValueError("match field and value are required")
        if not isinstance(updates, dict) or not updates or not isinstance(unique_fields, tuple) or not unique_fields:
            raise ValueError("updates and unique_fields are required")
        identity = tuple(updates.get(field) for field in unique_fields)
        if any(not isinstance(value, str) or not value for value in identity):
            raise ValueError("unique update fields must be non-empty strings")
        encoded_updates = json.dumps(updates, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT value_json FROM tenant_state WHERE tenant_id=? AND subject_id=? AND key=?",
                (tenant_id, subject_id, normalized_key),
            ).fetchone()
            current = [] if row is None else json.loads(row[0])
            if not isinstance(current, list) or any(not isinstance(entry, dict) for entry in current):
                raise ValueError("stored tenant list has an invalid shape")
            target = next((entry for entry in current if entry.get(match_field) == match_value), None)
            if target is None:
                connection.rollback()
                return False
            duplicate = next((
                entry for entry in current
                if entry is not target and all(
                    entry.get(field) == value for field, value in zip(unique_fields, identity)
                )
            ), None)
            if duplicate is not None:
                connection.rollback()
                raise ValueError("unique tenant list identity already exists")
            target.update(json.loads(encoded_updates))
            encoded = json.dumps(current, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
            connection.execute(
                """UPDATE tenant_state SET value_json=?, updated_at=CURRENT_TIMESTAMP
                WHERE tenant_id=? AND subject_id=? AND key=?""",
                (encoded, tenant_id, subject_id, normalized_key),
            )
            connection.commit()
        return True

    def delete(self, context: TenantContext, key: str) -> None:
        tenant_id, subject_id, normalized_key = self._scope(context, key)
        with self._lock, self._connect() as connection:
            connection.execute(
                "DELETE FROM tenant_state WHERE tenant_id=? AND subject_id=? AND key=?",
                (tenant_id, subject_id, normalized_key),
            )
