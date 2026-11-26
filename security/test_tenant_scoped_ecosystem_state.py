from __future__ import annotations

import tempfile
from concurrent.futures import ThreadPoolExecutor
import unittest
from pathlib import Path

from security.sqlite_tenant_storage import SQLiteTenantStorage
from security.tenant_context import TenantContext
from security.tenant_scoped_ecosystem_state import TenantScopedEcosystemState


class TenantScopedEcosystemStateTests(unittest.TestCase):
    def test_preferences_and_notifications_are_isolated_and_persistent(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tenant-state.sqlite3"
            first = TenantScopedEcosystemState(SQLiteTenantStorage(path))
            alice = TenantContext("tenant-a", "alice")
            bob = TenantContext("tenant-b", "bob")

            first.save_preferences(alice, {"language": "pt-BR"})
            first.save_preferences(bob, {"language": "en"})
            first.save_notifications(alice, [{"title": "Sinal mudou"}])
            first.save_notifications(bob, [{"title": "Other event"}])

            reopened = TenantScopedEcosystemState(SQLiteTenantStorage(path))
            self.assertEqual(reopened.load_preferences(alice), {"language": "pt-BR"})
            self.assertEqual(reopened.load_preferences(bob), {"language": "en"})
            self.assertEqual(reopened.load_notifications(alice), [{"title": "Sinal mudou"}])
            self.assertEqual(reopened.load_notifications(bob), [{"title": "Other event"}])

    def test_missing_or_untrusted_context_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            state = TenantScopedEcosystemState(
                SQLiteTenantStorage(Path(directory) / "tenant-state.sqlite3")
            )
            with self.assertRaises(PermissionError):
                state.load_preferences(None)  # type: ignore[arg-type]
            with self.assertRaises(PermissionError):
                state.load_notifications(None)  # type: ignore[arg-type]

    def test_invalid_shapes_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            state = TenantScopedEcosystemState(
                SQLiteTenantStorage(Path(directory) / "tenant-state.sqlite3")
            )
            tenant = TenantContext("tenant-a", "alice")
            with self.assertRaises(ValueError):
                state.save_preferences(tenant, [])  # type: ignore[arg-type]
            with self.assertRaises(ValueError):
                state.save_notifications(tenant, ["not-an-object"])  # type: ignore[list-item]

    def test_readiness_does_not_claim_production(self):
        with tempfile.TemporaryDirectory() as directory:
            state = TenantScopedEcosystemState(
                SQLiteTenantStorage(Path(directory) / "tenant-state.sqlite3")
            )
            status = state.readiness()
            self.assertFalse(status["production_ready"])
            self.assertFalse(status["production_durable"])
            self.assertFalse(status["legacy_data_migrated"])

    def test_append_notification_is_idempotent_and_tenant_scoped(self):
        with tempfile.TemporaryDirectory() as directory:
            state = TenantScopedEcosystemState(
                SQLiteTenantStorage(Path(directory) / "tenant-state.sqlite3")
            )
            alice = TenantContext("tenant-a", "alice")
            bob = TenantContext("tenant-a", "bob")
            item = {"notification_id": "market-eurusd-m5-1", "title": "Sinal mudou"}
            self.assertTrue(state.append_notification(alice, item))
            self.assertFalse(state.append_notification(alice, item))
            self.assertEqual(state.load_notifications(alice), [item])
            self.assertEqual(state.load_notifications(bob), [])

    def test_append_notification_rejects_missing_id_and_invalid_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            state = TenantScopedEcosystemState(
                SQLiteTenantStorage(Path(directory) / "tenant-state.sqlite3")
            )
            tenant = TenantContext("tenant-a", "alice")
            with self.assertRaises(ValueError):
                state.append_notification(tenant, {"title": "missing id"})
            with self.assertRaises(ValueError):
                state.append_notification(
                    tenant, {"notification_id": "n1"}, limit=0
                )


    def test_concurrent_notification_appends_do_not_lose_events(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tenant-state.sqlite3"
            tenant = TenantContext("tenant-a", "alice")
            states = [
                TenantScopedEcosystemState(SQLiteTenantStorage(path))
                for _ in range(8)
            ]

            def append(index):
                state = states[index % len(states)]
                return state.append_notification(
                    tenant,
                    {"notification_id": f"event-{index}", "title": f"Event {index}"},
                )

            with ThreadPoolExecutor(max_workers=12) as pool:
                outcomes = list(pool.map(append, range(80)))

            self.assertEqual(sum(outcomes), 80)
            notifications = states[0].load_notifications(tenant)
            self.assertEqual(len(notifications), 80)
            self.assertEqual(
                {item["notification_id"] for item in notifications},
                {f"event-{index}" for index in range(80)},
            )

    def test_concurrent_duplicate_notification_is_stored_once(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tenant-state.sqlite3"
            tenant = TenantContext("tenant-a", "alice")
            states = [
                TenantScopedEcosystemState(SQLiteTenantStorage(path))
                for _ in range(8)
            ]
            item = {"notification_id": "same-event", "title": "One event"}

            with ThreadPoolExecutor(max_workers=12) as pool:
                outcomes = list(
                    pool.map(
                        lambda index: states[index % len(states)].append_notification(
                            tenant, item
                        ),
                        range(40),
                    )
                )

            self.assertEqual(sum(outcomes), 1)
            self.assertEqual(states[0].load_notifications(tenant), [item])



if __name__ == "__main__":
    unittest.main()
