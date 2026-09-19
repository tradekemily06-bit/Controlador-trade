from core.p128_learning_source_gate import LearningSourceStatus, LearningSourceType
from core.scoped_learning_state import ScopedLearningState
from storage.scoped_state_store import SQLiteScopedStateStore


def test_persisted_learning_source_cannot_reenable_operation_authority(tmp_path):
    store = SQLiteScopedStateStore(tmp_path / "state.sqlite3")
    store.put(
        tenant_id="tenant-a",
        subject_id="user-a",
        namespace=ScopedLearningState.NAMESPACE,
        payload={
            "sources": {
                "knowledge-1": {
                    "source_id": "knowledge-1",
                    "source_type": LearningSourceType.LINK.value,
                    "uri": "https://example.com/knowledge",
                    "status": LearningSourceStatus.VALIDATED.value,
                    "content_verified": True,
                    "security_checked": True,
                    "knowledge_validated": True,
                    "operation_eligible": True,
                }
            },
            "resources": {},
            "observations": [],
            "activities": {},
            "attempts": [],
            "material_reviews": {},
        },
    )

    state = ScopedLearningState(state_store=store, require_durable=True)
    scope = state.get(tenant_id="tenant-a", subject_id="user-a")

    assert scope is not None
    assert scope.sources["knowledge-1"].operation_eligible is False
