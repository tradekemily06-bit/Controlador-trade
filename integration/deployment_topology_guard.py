"""Fail-closed guard for the currently supported SQLite deployment topology."""
from __future__ import annotations

import os


def validate_single_replica_sqlite_topology(
    environ: dict[str, str] | None = None,
) -> dict[str, object]:
    """Reject unsupported storage/topology declarations instead of silently ignoring them.

    The runtime is wired to local SQLite stores. Declaring PostgreSQL or another
    backend in configuration must not be mistaken for an active migration.
    SQLite leases and process locks coordinate only one shared host/runtime.
    Replica count is an operator declaration, not automatic replica discovery.
    """
    values = os.environ if environ is None else environ

    backend = str(values.get("CONTROLADOR_STORAGE_BACKEND", "sqlite")).strip().lower()
    if backend not in {"sqlite", "local_sqlite"}:
        raise RuntimeError(
            "unsupported CONTROLADOR_STORAGE_BACKEND: this runtime is still wired "
            "to local SQLite; a shared database backend cannot be declared ready "
            "until every runtime store, lease and outbox is migrated and tested"
        )

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
        "storage_backend": "LOCAL_SQLITE",
        "expected_replicas": replicas,
        "multi_replica_ready": False,
        "execution_authorized": False,
    }
