from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from core.ecosystem_notifications import EcosystemNotification, NotificationKind, NotificationSeverity
from security.sqlite_tenant_storage import SQLiteTenantStorage
from security.tenant_context import TenantContext
from security.tenant_scoped_ecosystem_state import TenantScopedEcosystemState
from integration.tenant_notification_dispatcher import TenantNotificationDispatcher


class TenantNotificationDispatcherTests(unittest.TestCase):
    def test_dispatch_requires_explicit_recipient_and_does_not_broadcast(self):
        with tempfile.TemporaryDirectory() as directory:
            state = TenantScopedEcosystemState(SQLiteTenantStorage(Path(directory) / "tenant.sqlite3"))
            dispatcher = TenantNotificationDispatcher(state)
            event = EcosystemNotification(
                notification_id="market-eurusd-m5-001",
                kind=NotificationKind.MARKET,
                severity=NotificationSeverity.IMPORTANT,
                title="Mudança de sinal",
                message="Revisão manual necessária.",
            )
            alice = TenantContext("tenant-a", "alice")
            bob = TenantContext("tenant-a", "bob")
            self.assertTrue(dispatcher.publish(alice, event))
            self.assertFalse(dispatcher.publish(alice, event))
            self.assertEqual(len(state.load_notifications(alice)), 1)
            self.assertEqual(state.load_notifications(bob), [])

    def test_dispatch_rejects_missing_or_invalid_context_and_event(self):
        with tempfile.TemporaryDirectory() as directory:
            state = TenantScopedEcosystemState(SQLiteTenantStorage(Path(directory) / "tenant.sqlite3"))
            dispatcher = TenantNotificationDispatcher(state)
            event = EcosystemNotification(
                notification_id="n1", kind=NotificationKind.SECURITY,
                severity=NotificationSeverity.CRITICAL, title="Aviso",
                message="Verificar acesso.",
            )
            with self.assertRaises(PermissionError):
                dispatcher.publish(None, event)  # type: ignore[arg-type]
            with self.assertRaises(TypeError):
                dispatcher.publish(TenantContext("t", "s"), {})  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
