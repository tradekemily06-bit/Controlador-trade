from pathlib import Path
from core.ecosystem_notifications import (
    EcosystemNotificationCenter,
    NotificationKind,
    NotificationSeverity,
)


def test_ecosystem_update_is_material_and_visible():
    center = EcosystemNotificationCenter()
    event = center.publish_ecosystem_update(
        "update-1",
        "Atualização do ecossistema disponível",
        "Uma atualização importante precisa ser aplicada.",
    )
    assert event.kind is NotificationKind.SYSTEM_UPDATE
    assert event.severity is NotificationSeverity.IMPORTANT
    assert event in center.visible()


def test_blocking_security_update_is_critical():
    center = EcosystemNotificationCenter()
    event = center.publish_security_update(
        "security-1", "Atualização de segurança", "Correção crítica necessária.", blocking=True
    )
    assert event.severity is NotificationSeverity.CRITICAL
    assert event in center.critical()


def test_security_updates_are_private_by_default(tmp_path: Path):
    from core.ecosystem_notifications import EcosystemNotificationCenter
    from storage.scoped_state_store import SQLiteScopedStateStore
    from security.http_identity import TrustedHttpIdentity, _current_identity

    center = EcosystemNotificationCenter(
        state_store=SQLiteScopedStateStore(tmp_path / "state.db"),
        require_durable=True,
    )
    token = _current_identity.set(TrustedHttpIdentity("subject", "tenant", "user"))
    try:
        center.publish_security_update("sec-1", "Security", "private security event")
        assert [item.notification_id for item in center.all()] == ["sec-1"]
    finally:
        _current_identity.reset(token)

    other = EcosystemNotificationCenter(
        state_store=SQLiteScopedStateStore(tmp_path / "state.db"),
        require_durable=True,
    )
    token = _current_identity.set(TrustedHttpIdentity("other-subject", "other-tenant", "user"))
    try:
        assert other.all() == ()
    finally:
        _current_identity.reset(token)
