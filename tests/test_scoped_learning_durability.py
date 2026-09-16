from __future__ import annotations

from core.learning_content import ContentType, LearningActivity, LearningResource
from core.p128_learning_source_gate import LearningSource, LearningSourceStatus, LearningSourceType
from core.scoped_learning_state import ScopedLearningState
from storage.scoped_state_store import SQLiteScopedStateStore


def test_learning_state_survives_restart_and_is_isolated(tmp_path):
    state = SQLiteScopedStateStore(tmp_path / "state.db")
    first = ScopedLearningState(state_store=state, require_durable=True)

    scope_a = first.get(tenant_id="tenant-a", subject_id="user-a")
    scope_a.sources["src-1"] = LearningSource("src-1", LearningSourceType.LINK, "https://example.com/a", LearningSourceStatus.VALIDATED, True, True, True, False)
    scope_a.resources["res-1"] = LearningResource("res-1", "A", ContentType.ARTICLE, source_url="https://example.com/a")
    scope_a.activities["act-1"] = LearningActivity("act-1", "Explain A")
    first.persist(tenant_id="tenant-a", subject_id="user-a")

    scope_b = first.get(tenant_id="tenant-b", subject_id="user-a")
    assert scope_b.sources == {}
    assert scope_b.resources == {}

    restarted = ScopedLearningState(state_store=state, require_durable=True)
    restored = restarted.get(tenant_id="tenant-a", subject_id="user-a")
    assert restored.sources["src-1"].knowledge_validated is True
    assert restored.resources["res-1"].title == "A"
    assert restored.activities["act-1"].prompt == "Explain A"


def test_durable_mode_rejects_unscoped_access():
    state = ScopedLearningState(require_durable=True)
    try:
        state.get(tenant_id="tenant-a", subject_id=None)
    except PermissionError:
        pass
    else:
        raise AssertionError("partial scope must be rejected")
