from __future__ import annotations

import pytest

from storage.production_provider import ProductionProviderConfig, build_production_provider


def test_unconfigured_provider_is_fail_closed() -> None:
    provider, policy = build_production_provider(ProductionProviderConfig("", None, False))
    assert provider is None
    assert policy.status()["status"] == "NOT_CONFIGURED"


def test_sqlite_provider_is_durable_and_tenant_scoped(tmp_path) -> None:
    provider, policy = build_production_provider(ProductionProviderConfig("sqlite", str(tmp_path / "data.sqlite3"), False))
    assert provider is not None
    assert policy.status()["status"] == "READY"


def test_sqlite_is_rejected_for_multi_instance() -> None:
    with pytest.raises(RuntimeError, match="multi-instance"):
        build_production_provider(ProductionProviderConfig("sqlite", "/tmp/controlador.sqlite3", True))


def test_unknown_provider_is_not_silently_accepted() -> None:
    with pytest.raises(RuntimeError, match="unsupported production storage provider"):
        build_production_provider(ProductionProviderConfig("unknown", "/tmp/data", False))
