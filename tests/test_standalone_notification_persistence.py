from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from core.ecosystem_notifications import (
    EcosystemNotification,
    NotificationKind,
    NotificationSeverity,
)
from core.ecosystem_state_store import EcosystemStateStore
from integration.ecosystem_service import EcosystemService


class StandaloneNotificationPersistenceTests(unittest.TestCase):
    def test_notifications_restore_after_service_restart_and_are_exposed(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "ecosystem-state.sqlite3"
            state = EcosystemStateStore(database)
            first = EcosystemService(notification_state_store=state)
            first.publish_notification(EcosystemNotification(
                notification_id="market-feed-down",
                kind=NotificationKind.MARKET,
                severity=NotificationSeverity.CRITICAL,
                title="Fonte de mercado indisponível",
                message="A análise está bloqueada até a fonte retornar.",
                requires_attention=True,
                blocking=True,
            ))
            self.assertEqual(first.notification_summary()["persistence"], "SQLITE")

            restarted = EcosystemService(
                notification_state_store=EcosystemStateStore(database)
            )
            items = restarted.notification_items(include_info=True)
            self.assertTrue(any(item["notification_id"] == "market-feed-down" for item in items))
            self.assertEqual(restarted.notification_summary()["by_severity"]["CRITICAL"], 1)
            self.assertEqual(restarted.system_status()["notification_persistence"], "SQLITE")
            self.assertFalse(any(item.get("execution_authorized", True) for item in items))

            from core.unified_intelligence import ApplicationArea
            from integration.standalone_application_factory import build_standalone_application
            app = build_standalone_application(ecosystem_service=restarted)
            cabin = app.handle(area=ApplicationArea.COMMAND_CABIN, task="verificar alertas")
            self.assertEqual(cabin["status"], "CONNECTED")
            self.assertEqual(cabin["result"]["notifications"]["persistence"], "SQLITE")
            self.assertTrue(any(
                item["notification_id"] == "market-feed-down"
                for item in cabin["result"]["notification_items"]
            ))


if __name__ == "__main__":
    unittest.main()
