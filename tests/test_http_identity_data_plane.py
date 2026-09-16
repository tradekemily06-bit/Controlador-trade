import pytest
from security.http_identity import TrustedHttpIdentity, _current_identity
from security.http_identity import PublicSaaSNotReady, require_tenant_scoped_data_plane

def test_public_saas_data_plane_requires_durable_provider(monkeypatch, tmp_path):
    monkeypatch.delenv("CONTROLADOR_PRODUCTION_STORE", raising=False)
    monkeypatch.delenv("CONTROLADOR_PRODUCTION_DB", raising=False)
    monkeypatch.delenv("CONTROLADOR_MULTI_INSTANCE", raising=False)
    with pytest.raises(PublicSaaSNotReady):
        require_tenant_scoped_data_plane()

def test_public_saas_data_plane_accepts_durable_single_instance_sqlite(monkeypatch, tmp_path):
    monkeypatch.setenv("CONTROLADOR_PRODUCTION_STORE", "sqlite")
    monkeypatch.setenv("CONTROLADOR_PRODUCTION_DB", str(tmp_path / "production.sqlite3"))
    monkeypatch.delenv("CONTROLADOR_MULTI_INSTANCE", raising=False)
    token = _current_identity.set(TrustedHttpIdentity("user-test", "tenant-test", "user"))
    try:
        require_tenant_scoped_data_plane()
    finally:
        _current_identity.reset(token)

def test_public_saas_data_plane_rejects_sqlite_multi_instance(monkeypatch, tmp_path):
    monkeypatch.setenv("CONTROLADOR_PRODUCTION_STORE", "sqlite")
    monkeypatch.setenv("CONTROLADOR_PRODUCTION_DB", str(tmp_path / "production.sqlite3"))
    monkeypatch.setenv("CONTROLADOR_MULTI_INSTANCE", "true")
    with pytest.raises(PublicSaaSNotReady):
        require_tenant_scoped_data_plane()
