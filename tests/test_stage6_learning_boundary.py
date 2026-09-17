from __future__ import annotations

from core.p128_learning_source_gate import (
    LearningSourceGate,
    LearningSourceStatus,
    LearningSourceType,
)


def test_validated_external_learning_never_becomes_operation_eligible():
    gate = LearningSourceGate()
    source = gate.intake(
        source_id="lesson-1",
        source_type=LearningSourceType.LINK,
        uri="https://example.com/lesson",
    )
    source = gate.validate_content(
        source,
        content_verified=True,
        security_checked=True,
    )
    source = gate.admit_knowledge(source, knowledge_validated=True)

    assert source.status is LearningSourceStatus.VALIDATED
    assert source.knowledge_validated is True
    assert source.operation_eligible is False


def test_learning_gate_forces_operation_eligibility_off_even_if_input_is_tainted():
    gate = LearningSourceGate()
    source = gate.intake(
        source_id="lesson-2",
        source_type=LearningSourceType.VIDEO,
        uri="https://example.com/video",
    )
    source = gate.validate_content(
        source,
        content_verified=True,
        security_checked=True,
    )
    tainted = type(source)(
        source.source_id,
        source.source_type,
        source.uri,
        source.status,
        source.content_verified,
        source.security_checked,
        True,
        True,
    )

    admitted = gate.admit_knowledge(tainted, knowledge_validated=True)

    assert admitted.status is LearningSourceStatus.VALIDATED
    assert admitted.knowledge_validated is True
    assert admitted.operation_eligible is False
