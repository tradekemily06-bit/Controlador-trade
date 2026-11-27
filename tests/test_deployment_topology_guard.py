from __future__ import annotations

import unittest

from integration.deployment_topology_guard import validate_single_replica_sqlite_topology


class DeploymentTopologyGuardTests(unittest.TestCase):
    def test_defaults_to_single_replica_and_never_claims_multi_replica_ready(self):
        result = validate_single_replica_sqlite_topology({})
        self.assertEqual(result["deployment_topology"], "SINGLE_HOST_SINGLE_RUNTIME")
        self.assertEqual(result["storage_backend"], "LOCAL_SQLITE")
        self.assertEqual(result["expected_replicas"], 1)
        self.assertFalse(result["multi_replica_ready"])
        self.assertFalse(result["execution_authorized"])

    def test_accepts_explicit_local_sqlite_aliases_only(self):
        for backend in ("sqlite", "local_sqlite", " SQLITE "):
            with self.subTest(backend=backend):
                result = validate_single_replica_sqlite_topology(
                    {"CONTROLADOR_STORAGE_BACKEND": backend}
                )
                self.assertEqual(result["storage_backend"], "LOCAL_SQLITE")

    def test_rejects_declared_shared_backend_until_it_is_really_wired(self):
        for backend in ("postgres", "postgresql", "mysql", "redis", ""):
            with self.subTest(backend=backend), self.assertRaisesRegex(
                RuntimeError, "unsupported CONTROLADOR_STORAGE_BACKEND"
            ):
                validate_single_replica_sqlite_topology(
                    {"CONTROLADOR_STORAGE_BACKEND": backend}
                )

    def test_rejects_declared_multiple_replicas_until_shared_storage_exists(self):
        with self.assertRaisesRegex(RuntimeError, "multi-replica startup is blocked"):
            validate_single_replica_sqlite_topology({"CONTROLADOR_EXPECTED_REPLICAS": "2"})

    def test_rejects_invalid_or_non_positive_replica_count(self):
        for value in ("", "many", "0", "-1"):
            with self.subTest(value=value), self.assertRaisesRegex(
                RuntimeError, "must be a positive integer"
            ):
                validate_single_replica_sqlite_topology(
                    {"CONTROLADOR_EXPECTED_REPLICAS": value}
                )
