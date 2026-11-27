from __future__ import annotations

import pytest

from security.tenant_context import TenantContext, build_trusted_tenant_context


def test_tenant_context_trims_identity_components():
    context = TenantContext(" tenant-a ", " user-1 ")
    assert context.tenant_id == "tenant-a"
    assert context.subject_id == "user-1"


@pytest.mark.parametrize(
    "tenant_id,subject_id",
    [
        ("", "user-1"),
        ("tenant-a", " "),
        ("x" * 257, "user-1"),
        ("tenant-a", "u" * 257),
        ("tenant\nadmin", "user-1"),
        ("tenant-a", "user\x00admin"),
        (None, "user-1"),
        ("tenant-a", 42),
    ],
)
def test_tenant_context_rejects_invalid_or_unbounded_identity_components(
    tenant_id, subject_id
):
    with pytest.raises(ValueError):
        TenantContext(tenant_id, subject_id)


def test_trusted_context_builder_fails_closed_on_invalid_claims():
    assert build_trusted_tenant_context(
        authenticated=True, tenant_id="tenant\nadmin", subject_id="user-1"
    ) is None
    assert build_trusted_tenant_context(
        authenticated=True, tenant_id="tenant-a", subject_id="x" * 257
    ) is None
    assert build_trusted_tenant_context(
        authenticated=False, tenant_id="tenant-a", subject_id="user-1"
    ) is None
