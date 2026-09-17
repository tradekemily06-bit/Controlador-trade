from __future__ import annotations

from core.ecosystem_onboarding import EcosystemOnboarding, OnboardingSection
from core.ecosystem_notifications import (
    EcosystemNotification,
    EcosystemNotificationCenter,
    NotificationKind,
    NotificationSeverity,
)


def test_first_use_guide_is_complete_but_never_authorizes_execution():
    guide = EcosystemOnboarding().build_first_use_guide()

    assert guide.execution_authorized is False
    assert guide.steps
    assert OnboardingSection.OPERATION in {step.location for step in guide.steps}
    assert OnboardingSection.SECURITY in {step.location for step in guide.steps}
    assert all(step.technical_details_hidden for step in guide.steps)


def test_critical_notifications_remain_visible_without_polluting_info_surface():
    center = EcosystemNotificationCenter()
    center.publish(EcosystemNotification("info-1", NotificationKind.LEARNING, NotificationSeverity.INFO, "Dica", "Conteúdo de estudo."))
    center.publish(EcosystemNotification("critical-1", NotificationKind.SECURITY, NotificationSeverity.CRITICAL, "Bloqueio", "Execução bloqueada.", requires_attention=True, blocking=True))

    assert [item.notification_id for item in center.visible()] == ["critical-1"]
    assert [item.notification_id for item in center.critical()] == ["critical-1"]
    assert [item.notification_id for item in center.all()] == ["info-1", "critical-1"]
