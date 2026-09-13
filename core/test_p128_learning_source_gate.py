from core.p128_learning_source_gate import LearningSourceGate, LearningSourceStatus, LearningSourceType


def test_external_source_starts_quarantined_and_never_operation_eligible():
    gate = LearningSourceGate()
    source = gate.intake(
        source_id="video-1",
        source_type=LearningSourceType.VIDEO,
        uri="https://example.com/video",
    )
    assert source.status is LearningSourceStatus.QUARANTINED
    assert source.operation_eligible is False


def test_insecure_or_non_https_source_is_blocked():
    source = LearningSourceGate().intake(
        source_id="link-1",
        source_type=LearningSourceType.LINK,
        uri="http://example.com/article",
    )
    assert source.status is LearningSourceStatus.BLOCKED
    assert source.operation_eligible is False


def test_source_needs_security_and_content_validation():
    gate = LearningSourceGate()
    source = gate.intake(
        source_id="doc-1",
        source_type=LearningSourceType.DOCUMENT,
        uri="https://example.com/doc",
    )
    partial = gate.validate_content(source, content_verified=True, security_checked=False)
    assert partial.status is LearningSourceStatus.QUARANTINED
    assert partial.knowledge_validated is False
    assert partial.operation_eligible is False

    validated = gate.validate_content(source, content_verified=True, security_checked=True)
    assert validated.status is LearningSourceStatus.VALIDATED
    assert validated.operation_eligible is False


def test_validated_source_still_requires_knowledge_validation_and_never_grants_execution():
    gate = LearningSourceGate()
    source = gate.intake(
        source_id="link-2",
        source_type=LearningSourceType.LINK,
        uri="https://example.com/research",
    )
    source = gate.validate_content(source, content_verified=True, security_checked=True)
    admitted = gate.admit_knowledge(source, knowledge_validated=True)

    assert admitted.knowledge_validated is True
    assert admitted.operation_eligible is False
