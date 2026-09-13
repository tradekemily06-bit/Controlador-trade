import pytest

from core.learning_content import ContentType, LearningActivity, LearningContentError, LearningObservation, LearningResource, normalize_tags


def test_resource_accepts_video_and_http_url():
    resource = LearningResource("video-1", "Aula", ContentType.VIDEO, "https://example.com/video", tags=normalize_tags(["pavio", "rejeicao", "pavio"]))
    assert resource.content_type is ContentType.VIDEO
    assert resource.tags == ("pavio", "rejeicao")


def test_resource_rejects_non_http_url():
    with pytest.raises(LearningContentError):
        LearningResource("x", "Fonte", ContentType.OTHER, "file:///tmp/a")


def test_observation_requires_explicit_validation():
    observation = LearningObservation("video-1", "O material descreve uma rejeicao", ("rejeicao",), confidence=0.8)
    assert observation.validated is False


def test_activity_accepts_open_concept_vocabulary():
    activity = LearningActivity("quiz-1", "Identifique o contexto", ("conceito-novo",))
    assert activity.expected_concepts == ("conceito-novo",)


def test_invalid_confidence_is_rejected():
    with pytest.raises(LearningContentError):
        LearningObservation("x", "y", confidence=1.1)
