from __future__ import annotations

import pytest

from storage.scoped_state_store import SQLiteScopedStateStore
from storage.sqlite_production_store import SQLiteProductionStore


def test_production_records_are_isolated_by_tenant_and_subject(tmp_path):
    store = SQLiteProductionStore(tmp_path / "production.sqlite")
    store.save({"record_id": "same-id", "value": "alpha"}, tenant_id="tenant-a", subject_id="user-a")
    store.save({"record_id": "same-id", "value": "beta"}, tenant_id="tenant-b", subject_id="user-b")

    assert store.load("same-id", tenant_id="tenant-a", subject_id="user-a")["value"] == "alpha"
    assert store.load("same-id", tenant_id="tenant-b", subject_id="user-b")["value"] == "beta"
    assert store.load("same-id", tenant_id="tenant-a", subject_id="user-b") is None
    assert store.list(tenant_id="tenant-a", subject_id="user-a") == [
        {"record_id": "same-id", "value": "alpha"}
    ]


def test_scoped_state_is_isolated_by_tenant_subject_and_namespace(tmp_path):
    store = SQLiteScopedStateStore(tmp_path / "state.sqlite")
    store.put(tenant_id="tenant-a", subject_id="user-a", namespace="prefs", payload={"x": 1})
    store.put(tenant_id="tenant-b", subject_id="user-b", namespace="prefs", payload={"x": 2})

    assert store.get(tenant_id="tenant-a", subject_id="user-a", namespace="prefs") == {"x": 1}
    assert store.get(tenant_id="tenant-b", subject_id="user-b", namespace="prefs") == {"x": 2}
    assert store.get(tenant_id="tenant-a", subject_id="user-b", namespace="prefs") is None


@pytest.mark.parametrize(
    "operation",
    ["load", "list"],
)
def test_production_store_requires_both_scope_dimensions(tmp_path, operation):
    store = SQLiteProductionStore(tmp_path / "production.sqlite")
    if operation == "load":
        with pytest.raises(ValueError):
            store.load("record", tenant_id="", subject_id="user")
        with pytest.raises(ValueError):
            store.load("record", tenant_id="tenant", subject_id="")
    else:
        with pytest.raises(ValueError):
            store.list(tenant_id="", subject_id="user")
        with pytest.raises(ValueError):
            store.list(tenant_id="tenant", subject_id="")


def test_scoped_state_requires_both_scope_dimensions(tmp_path):
    store = SQLiteScopedStateStore(tmp_path / "state.sqlite")
    with pytest.raises(PermissionError):
        store.get(tenant_id=None, subject_id="user", namespace="prefs")
    with pytest.raises(PermissionError):
        store.put(tenant_id="tenant", subject_id=None, namespace="prefs", payload={})
