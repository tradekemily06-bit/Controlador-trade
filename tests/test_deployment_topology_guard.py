from __future__ import annotations

import unittest

from integration.deployment_topology_guard import validate_single_replica_sqlite_topology


class DeploymentTopologyGuardTests(unittest.TestCase):
    def test_defaults_to_single_replica_and_never_claims_multi_replica_ready(self):
        result = validate_single_replica_sqlite_topology({})
        self.assertEqual(result["deployment_topology"], "SINGLE_HOST_SINGLE_RUNTIME")
        self.assertEqual(result["expected_replicas"], 1)
        self.assertFalse(result["multi_replica_ready"])
        self.assertFalse(result["execution_authorized"])

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
