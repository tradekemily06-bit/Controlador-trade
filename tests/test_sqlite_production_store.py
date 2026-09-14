import pytest

from storage.sqlite_production_store import SQLiteProductionStore


def test_sqlite_store_survives_restart_and_is_scope_isolated(tmp_path):
    path = tmp_path / "production.sqlite3"
    store = SQLiteProductionStore(path)
    store.save({"record_id": "r1", "value": "tenant-a"}, tenant_id="tenant-a", subject_id="user-a")
    store.save({"record_id": "r1", "value": "tenant-b"}, tenant_id="tenant-b", subject_id="user-b")

    restarted = SQLiteProductionStore(path)
    assert restarted.load("r1", tenant_id="tenant-a", subject_id="user-a")["value"] == "tenant-a"
    assert restarted.load("r1", tenant_id="tenant-b", subject_id="user-b")["value"] == "tenant-b"
    assert restarted.load("r1", tenant_id="tenant-a", subject_id="user-b") is None
    assert restarted.list(tenant_id="tenant-a", subject_id="user-a") == [{"record_id": "r1", "value": "tenant-a"}]


def test_sqlite_store_requires_nonempty_scope_and_positive_limit(tmp_path):
    store = SQLiteProductionStore(tmp_path / "production.sqlite3")
    with pytest.raises(ValueError):
        store.save({"record_id": "r1"}, tenant_id="", subject_id="user")
    with pytest.raises(ValueError):
        store.list(tenant_id="tenant", subject_id="user", limit=0)
