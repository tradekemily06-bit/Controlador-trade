from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from urllib.parse import urlparse


class LearningContentError(ValueError):
    pass


class ContentType(str, Enum):
    VIDEO = "VIDEO"
    ARTICLE = "ARTICLE"
    DOCUMENT = "DOCUMENT"
    IMAGE = "IMAGE"
    NOTE = "NOTE"
    OTHER = "OTHER"


class LearningStatus(str, Enum):
    RECEIVED = "RECEIVED"
    ANALYZED = "ANALYZED"
    NEEDS_REVIEW = "NEEDS_REVIEW"


@dataclass(frozen=True)
class LearningResource:
    """Study source metadata. Remote URLs are not fetched by this model."""

    resource_id: str
    title: str
    content_type: ContentType
    source_url: str | None = None
    source_name: str | None = None
    status: LearningStatus = LearningStatus.RECEIVED
    tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.resource_id.strip():
            raise LearningContentError("resource_id must not be empty")
        if not self.title.strip():
            raise LearningContentError("title must not be empty")
        if self.source_url is not None:
            parsed = urlparse(self.source_url)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise LearningContentError("source_url must be an absolute HTTP(S) URL")


@dataclass(frozen=True)
class LearningObservation:
    """Knowledge extracted from study material, requiring validation before reuse."""

    resource_id: str
    statement: str
    concepts: tuple[str, ...] = ()
    evidence: str | None = None
    confidence: float | None = None
    validated: bool = False

    def __post_init__(self) -> None:
        if not self.resource_id.strip() or not self.statement.strip():
            raise LearningContentError("resource_id and statement are required")
        if self.confidence is not None and not 0.0 <= self.confidence <= 1.0:
            raise LearningContentError("confidence must be between 0 and 1")


@dataclass(frozen=True)
class LearningActivity:
    """Study activity; results are educational data only."""

    activity_id: str
    prompt: str
    expected_concepts: tuple[str, ...] = ()
    difficulty: str = "UNSPECIFIED"

    def __post_init__(self) -> None:
        if not self.activity_id.strip() or not self.prompt.strip():
            raise LearningContentError("activity_id and prompt are required")


@dataclass(frozen=True)
class LearningAttempt:
    activity_id: str
    answer: str
    correct: bool | None = None
    feedback: str = ""

    def __post_init__(self) -> None:
        if not self.activity_id.strip():
            raise LearningContentError("activity_id must not be empty")


def normalize_tags(tags: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(tag.strip() for tag in tags if tag.strip()))
