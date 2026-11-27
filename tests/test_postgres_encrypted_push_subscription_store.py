from __future__ import annotations

import sqlite3

import pytest

from security.postgres_encrypted_push_subscription_store import (
    PostgresEncryptedPushSubscriptionStore,
)
from security.tenant_context import TenantContext


class _Cursor:
    def __init__(self, cursor):
        self._cursor = cursor

    def execute(self, sql, params=()):
        self._cursor.execute(sql.replace("%s", "?"), params)
        return self

    def fetchall(self):
        return self._cursor.fetchall()

    @property
    def rowcount(self):
        return self._cursor.rowcount

    def close(self):
        self._cursor.close()


class _Connection:
    def __init__(self, path):
        self._connection = sqlite3.connect(path)

    def cursor(self):
        return _Cursor(self._connection.cursor())

    def commit(self):
        self._connection.commit()

    def rollback(self):
        self._connection.rollback()

    def close(self):
        self._connection.close()


class _SharedTestPostgresFactory:
    shared_database = True
    production_durable = True

    def __init__(self, path):
        self.path = path

    def __call__(self):
        return _Connection(self.path)


def _store(tmp_path, *, key=None, version="v1"):
    factory = _SharedTestPostgresFactory(tmp_path / "push.sqlite3")
    secret = key or (b"K" * 32)
    store = PostgresEncryptedPushSubscriptionStore(
        factory,
        lambda requested_version: secret if requested_version == version else None,
        key_version=version,
    )
    store.initialize_schema()
    return store


def test_store_encrypts_subscription_and_scopes_rows_to_tenant_subject(tmp_path):
    store = _store(tmp_path)
    owner = TenantContext("tenant-a", "subject-1")
    other_subject = TenantContext("tenant-a", "subject-2")
    other_tenant = TenantContext("tenant-b", "subject-1")
    record = {
        "endpoint": "https://updates.push.services.mozilla.com/push/v1/private-token",
        "keys": {"p256dh": "public-material", "auth": "auth-material"},
        "status": "ACTIVE",
        "expiration_time": None,
    }

    store.put_for_owner(owner, "device-1", record)

    assert store.list_for_owner(owner) == [{"device_id": "device-1", **record}]
    assert store.list_for_owner(other_subject) == []
    assert store.list_for_owner(other_tenant) == []

    raw = sqlite3.connect(tmp_path / "push.sqlite3").execute(
        "SELECT encrypted_payload FROM controlador_push_subscriptions"
    ).fetchone()[0]
    assert b"private-token" not in raw
    assert b"public-material" not in raw
    assert b"auth-material" not in raw


def test_store_upserts_and_deletes_only_the_exact_owner_device(tmp_path):
    store = _store(tmp_path)
    owner = TenantContext("tenant-a", "subject-1")
    other = TenantContext("tenant-a", "subject-2")
    store.put_for_owner(owner, "device-1", {"status": "ACTIVE", "endpoint": "https://one"})
    store.put_for_owner(owner, "device-1", {"status": "ROTATED", "endpoint": "https://two"})
    store.put_for_owner(other, "device-1", {"status": "ACTIVE", "endpoint": "https://other"})

    assert store.list_for_owner(owner)[0]["endpoint"] == "https://two"
    assert store.delete_for_owner(owner, "device-1") is True
    assert store.delete_for_owner(owner, "device-1") is False
    assert store.list_for_owner(other)[0]["endpoint"] == "https://other"


def test_store_rejects_unattested_database_provider_and_invalid_key(tmp_path):
    class LocalFactory:
        def __call__(self):
            return _Connection(tmp_path / "local.sqlite3")

    with pytest.raises(RuntimeError, match="shared PostgreSQL"):
        PostgresEncryptedPushSubscriptionStore(
            LocalFactory(), lambda version: b"K" * 32, key_version="v1"
        )

    factory = _SharedTestPostgresFactory(tmp_path / "push.sqlite3")
    with pytest.raises(RuntimeError, match="32 bytes"):
        PostgresEncryptedPushSubscriptionStore(
            factory, lambda version: b"short", key_version="v1"
        )


def test_store_authenticates_ciphertext_and_rejects_wrong_owner_context(tmp_path):
    store = _store(tmp_path)
    owner = TenantContext("tenant-a", "subject-1")
    store.put_for_owner(owner, "device-1", {"status": "ACTIVE"})

    db = sqlite3.connect(tmp_path / "push.sqlite3")
    db.execute(
        "UPDATE controlador_push_subscriptions SET encrypted_payload=?",
        (b"tampered-ciphertext",),
    )
    db.commit()
    db.close()

    with pytest.raises(RuntimeError, match="could not be authenticated"):
        store.list_for_owner(owner)

    with pytest.raises(PermissionError):
        store.list_for_owner(None)
