from core.learning_material_review import (
    EffectivenessVerdict,
    KnowledgeReference,
    LearningMaterialReviewer,
    MaterialEffectivenessReview,
    MaterialVerdict,
)
from core.scoped_learning_state import ScopedLearningState


class MemoryStateStore:
    def __init__(self):
        self.data = {}

    def get(self, *, tenant_id, subject_id, namespace):
        return self.data.get((tenant_id, subject_id, namespace))

    def put(self, *, tenant_id, subject_id, namespace, payload):
        self.data[(tenant_id, subject_id, namespace)] = payload


def _review(resource_id):
    return LearningMaterialReviewer().review(
        resource_id=resource_id,
        claims=["Risco e tamanho da posição devem ser controlados"],
        references=[KnowledgeReference("risk-1", "Risco e tamanho da posição devem ser controlados")],
        effectiveness=MaterialEffectivenessReview(
            EffectivenessVerdict.NOT_ESTABLISHED,
            "Ainda não há amostra suficiente.",
        ),
        material_content_verified=True,
    )


def test_material_review_round_trips_and_never_restores_execution_authority():
    store = MemoryStateStore()
    first = ScopedLearningState(state_store=store, require_durable=True)
    scope = first.get(tenant_id="tenant-a", subject_id="user-a")
    scope.material_reviews["video-1"] = _review("video-1")
    first.persist(tenant_id="tenant-a", subject_id="user-a")

    second = ScopedLearningState(state_store=store, require_durable=True)
    restored = second.get(tenant_id="tenant-a", subject_id="user-a")
    assert restored.material_reviews["video-1"].overall_verdict is MaterialVerdict.KNOWN
    assert restored.material_reviews["video-1"].operation_authorized is False


def test_material_reviews_are_isolated_by_tenant_and_subject():
    store = MemoryStateStore()
    state = ScopedLearningState(state_store=store, require_durable=True)
    state.get(tenant_id="tenant-a", subject_id="user-a").material_reviews["a"] = _review("a")
    state.persist(tenant_id="tenant-a", subject_id="user-a")

    assert state.get(tenant_id="tenant-b", subject_id="user-a").material_reviews == {}
    assert state.get(tenant_id="tenant-a", subject_id="user-b").material_reviews == {}


def test_concurrent_scopes_merge_material_reviews_without_dropping_either():
    store = MemoryStateStore()
    left = ScopedLearningState(state_store=store, require_durable=True)
    right = ScopedLearningState(state_store=store, require_durable=True)
    left.get(tenant_id="tenant-a", subject_id="user-a").material_reviews["left"] = _review("left")
    right.get(tenant_id="tenant-a", subject_id="user-a").material_reviews["right"] = _review("right")

    left.persist(tenant_id="tenant-a", subject_id="user-a")
    right.persist(tenant_id="tenant-a", subject_id="user-a")

    final = ScopedLearningState(state_store=store, require_durable=True).get(
        tenant_id="tenant-a", subject_id="user-a"
    )
    assert set(final.material_reviews) == {"left", "right"}
