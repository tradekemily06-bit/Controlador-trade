import pytest

from storage.production_provider import ProductionProviderConfig, build_production_provider


def test_sqlite_provider_is_ready_only_for_single_instance(tmp_path):
    provider, policy = build_production_provider(
        ProductionProviderConfig("sqlite", str(tmp_path / "production.db"), False)
    )
    assert provider is not None
    assert policy.provider_configured is True
    assert policy.tenant_scoped is True
    assert policy.durable is True


def test_sqlite_provider_fails_closed_for_multi_instance(tmp_path):
    with pytest.raises(RuntimeError, match="multi-instance"):
        build_production_provider(
            ProductionProviderConfig("sqlite", str(tmp_path / "production.db"), True)
        )


def test_unconfigured_provider_never_falls_back_to_memory():
    provider, policy = build_production_provider(
        ProductionProviderConfig("", None, False)
    )
    assert provider is None
    assert policy.provider_configured is False
    assert policy.durable is False


def test_unknown_provider_fails_closed():
    with pytest.raises(RuntimeError, match="unsupported"):
        build_production_provider(
            ProductionProviderConfig("unknown", "/tmp/ignored.db", False)
        )
