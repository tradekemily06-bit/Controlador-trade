from __future__ import annotations

import pytest

from storage.scoped_state_store import SQLiteScopedStateStore


def test_state_survives_restart_and_isolated_by_tenant_subject(tmp_path):
    path = tmp_path / "state.db"
    first = SQLiteScopedStateStore(path)
    first.put(tenant_id="tenant-a", subject_id="user-a", namespace="preferences", payload={"theme": "dark"})

    second = SQLiteScopedStateStore(path)
    assert second.get(tenant_id="tenant-a", subject_id="user-a", namespace="preferences") == {"theme": "dark"}
    assert second.get(tenant_id="tenant-a", subject_id="user-b", namespace="preferences") is None
    assert second.get(tenant_id="tenant-b", subject_id="user-a", namespace="preferences") is None


def test_partial_scope_is_rejected(tmp_path):
    store = SQLiteScopedStateStore(tmp_path / "state.db")
    with pytest.raises(PermissionError):
        store.get(tenant_id="tenant-a", subject_id=None, namespace="preferences")
    with pytest.raises(PermissionError):
        store.put(tenant_id=None, subject_id="user-a", namespace="preferences", payload={})


def test_namespace_is_required(tmp_path):
    store = SQLiteScopedStateStore(tmp_path / "state.db")
    with pytest.raises(ValueError):
        store.put(tenant_id="tenant-a", subject_id="user-a", namespace="", payload={})
