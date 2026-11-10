from threading import RLock

import pytest

from core.ecosystem_notifications import EcosystemNotificationCenter
from core.ecosystem_state_store import NotificationHistoryUnavailableError
from integration.ecosystem_configuration_runtime import ConfiguredEcosystemService


class FailingNotificationStore:
    def save_notifications(self, items):
        raise NotificationHistoryUnavailableError("storage unavailable")


def build_service():
    service = ConfiguredEcosystemService.__new__(ConfiguredEcosystemService)
    service.state_store = FailingNotificationStore()
    service.notifications = EcosystemNotificationCenter()
    service._notification_history_lock = RLock()
    return service


@pytest.mark.parametrize(
    "publish",
    [
        lambda service: service.publish_ecosystem_update(
            "Atualização", "Não deve aparecer sem persistência"
        ),
        lambda service: service.publish_material_event(
            "RISK", "Risco", "Não deve aparecer sem persistência", critical=True
        ),
    ],
    ids=["ecosystem-update", "material-event"],
)
def test_failed_durable_write_never_publishes_notification(publish):
    service = build_service()

    with pytest.raises(NotificationHistoryUnavailableError):
        publish(service)

    assert service.notifications.all() == ()
