from __future__ import annotations

import ast
from pathlib import Path

import pytest

from core.ecosystem_onboarding import EcosystemOnboarding
from core.ecosystem_preferences import EcosystemPreferencesStore
from core.ecosystem_notifications import (
    EcosystemNotification,
    EcosystemNotificationCenter,
    NotificationKind,
    NotificationSeverity,
)


PRODUCT_SURFACES = (
    Path("core/ecosystem_onboarding.py"),
    Path("core/ecosystem_notifications.py"),
    Path("core/ecosystem_preferences.py"),
)


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    return imported


def test_product_surfaces_do_not_import_execution_authority():
    for path in PRODUCT_SURFACES:
        imports = _imports(path)
        assert not any(
            module == "execution"
            or module.startswith("execution.")
            or module.startswith("core.execution")
            for module in imports
        ), f"{path} must not depend directly on execution authority"


def test_onboarding_is_navigation_only():
    guide = EcosystemOnboarding().build_first_use_guide()
    assert guide.execution_authorized is False
    assert all(step.technical_details_hidden for step in guide.steps)


def test_preferences_cannot_turn_on_real_or_autonomous_execution():
    store = EcosystemPreferencesStore()
    with pytest.raises(ValueError, match="REAL"):
        store.update(real_execution_enabled=True)
    with pytest.raises(ValueError, match="autonomous"):
        store.update(autonomous_operation_enabled=True)
    assert store.preferences.real_execution_enabled is False
    assert store.preferences.autonomous_operation_enabled is False


def test_critical_notification_remains_visible_even_when_info_is_hidden():
    center = EcosystemNotificationCenter()
    center.publish(EcosystemNotification("info", NotificationKind.LEARNING, NotificationSeverity.INFO, "Info", "study"))
    center.publish(EcosystemNotification("critical", NotificationKind.SECURITY, NotificationSeverity.CRITICAL, "Bloqueio", "Execução bloqueada", requires_attention=True, blocking=True))
    assert [item.notification_id for item in center.visible()] == ["critical"]
    assert center.critical()[0].blocking is True
