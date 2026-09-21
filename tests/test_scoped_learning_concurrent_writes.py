from core.learning_content import ContentType, LearningObservation, LearningResource
from core.scoped_learning_state import ScopedLearningState


class MemoryStateStore:
    def __init__(self):
        self.data = {}

    def get(self, *, tenant_id, subject_id, namespace):
        value = self.data.get((tenant_id, subject_id, namespace))
        return None if value is None else dict(value)

    def put(self, *, tenant_id, subject_id, namespace, payload):
        self.data[(tenant_id, subject_id, namespace)] = dict(payload)

    def update(self, *, tenant_id, subject_id, namespace, updater):
        key = (tenant_id, subject_id, namespace)
        value = updater(self.data.get(key))
        self.data[key] = dict(value)
        return dict(value)


def test_concurrent_scoped_learning_writes_are_merged_not_lost():
    store = MemoryStateStore()
    first = ScopedLearningState(state_store=store, require_durable=True)
    second = ScopedLearningState(state_store=store, require_durable=True)

    first_scope = first.get(tenant_id="tenant-a", subject_id="user-a")
    second_scope = second.get(tenant_id="tenant-a", subject_id="user-a")

    first_scope.resources["r1"] = LearningResource("r1", "First", ContentType.NOTE)
    first_scope.observations.append(LearningObservation("r1", "First observation"))
    first.persist(tenant_id="tenant-a", subject_id="user-a")

    second_scope.resources["r2"] = LearningResource("r2", "Second", ContentType.NOTE)
    second_scope.observations.append(LearningObservation("r2", "Second observation"))
    second.persist(tenant_id="tenant-a", subject_id="user-a")

    third = ScopedLearningState(state_store=store, require_durable=True)
    merged = third.get(tenant_id="tenant-a", subject_id="user-a")

    assert set(merged.resources) == {"r1", "r2"}
    assert {item.statement for item in merged.observations} == {"First observation", "Second observation"}
