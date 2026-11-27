"""Fail-closed guard for the currently supported SQLite deployment topology."""
from __future__ import annotations

import os


def validate_single_replica_sqlite_topology(
    environ: dict[str, str] | None = None,
) -> dict[str, object]:
    """Reject declared multi-replica deployments until shared transactional storage exists.

    SQLite leases and process locks coordinate only one shared host/runtime.
    This guard does not detect replicas automatically; operators must declare
    the intended replica count through CONTROLADOR_EXPECTED_REPLICAS.
    """
    values = os.environ if environ is None else environ
    raw = values.get("CONTROLADOR_EXPECTED_REPLICAS", "1")
    try:
        replicas = int(raw)
    except (TypeError, ValueError) as exc:
        raise RuntimeError("CONTROLADOR_EXPECTED_REPLICAS must be a positive integer") from exc
    if replicas < 1:
        raise RuntimeError("CONTROLADOR_EXPECTED_REPLICAS must be a positive integer")
    if replicas > 1:
        raise RuntimeError(
            "multi-replica startup is blocked: this runtime still uses local SQLite; "
            "configure a shared transactional database, distributed leases, shared "
            "notification outbox and durable KMS-backed OAuth storage first"
        )
    return {
        "deployment_topology": "SINGLE_HOST_SINGLE_RUNTIME",
        "expected_replicas": replicas,
        "multi_replica_ready": False,
        "execution_authorized": False,
    }
