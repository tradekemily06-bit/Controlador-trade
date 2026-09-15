from core.ecosystem_notifications import EcosystemNotification, EcosystemNotificationCenter, NotificationKind, NotificationSeverity
from core.scoped_learning_state import ScopedLearningState


def test_learning_scope_cache_is_bounded():
    state = ScopedLearningState(cache_size=2)
    state.get(tenant_id="tenant-a", subject_id="user-a")
    state.get(tenant_id="tenant-b", subject_id="user-b")
    state.get(tenant_id="tenant-c", subject_id="user-c")
    assert len(state._scopes) == 2
    assert ("tenant-a", "user-a") not in state._scopes
    assert ("tenant-c", "user-c") in state._scopes


def test_notification_scope_cache_is_bounded():
    center = EcosystemNotificationCenter(cache_size=2)
    from security.http_identity import TrustedHttpIdentity, _current_identity
    token = _current_identity.set(TrustedHttpIdentity("user-a", "tenant-a", "user"))
    try:
        center.publish(EcosystemNotification("n-a", NotificationKind.LEARNING, NotificationSeverity.INFO, "A", "A"))
        center._current()
        _current_identity.set(TrustedHttpIdentity("user-b", "tenant-b", "user"))
        center.publish(EcosystemNotification("n-b", NotificationKind.LEARNING, NotificationSeverity.INFO, "B", "B"))
        _current_identity.set(TrustedHttpIdentity("user-c", "tenant-c", "user"))
        center.publish(EcosystemNotification("n-c", NotificationKind.LEARNING, NotificationSeverity.INFO, "C", "C"))
        assert len(center._scoped_notifications) == 2
        assert ("tenant-a", "user-a") not in center._scoped_notifications
        assert ("tenant-c", "user-c") in center._scoped_notifications
    finally:
        _current_identity.reset(token)
