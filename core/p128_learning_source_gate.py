from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from urllib.parse import urlparse


class LearningSourceType(str, Enum):
    VIDEO = "VIDEO"
    LINK = "LINK"
    DOCUMENT = "DOCUMENT"


class LearningSourceStatus(str, Enum):
    BLOCKED = "BLOCKED"
    QUARANTINED = "QUARANTINED"
    VALIDATED = "VALIDATED"


@dataclass(frozen=True)
class LearningSource:
    source_id: str
    source_type: LearningSourceType
    uri: str
    status: LearningSourceStatus
    content_verified: bool = False
    security_checked: bool = False
    knowledge_validated: bool = False
    operation_eligible: bool = False


class LearningSourceGate:
    """Security/learning boundary for external educational material.

    A URL or video is never allowed to become an operation directly. It must first
    be safely handled, its content verified, and any extracted market claim must
    pass the normal hypothesis/validation chain. This gate deliberately has no
    execution authority.
    """

    def intake(self, *, source_id: str, source_type: LearningSourceType, uri: str) -> LearningSource:
        if not isinstance(source_type, LearningSourceType):
            raise ValueError("invalid source type")
        if not isinstance(source_id, str) or not source_id.strip():
            raise ValueError("source_id is required")
        if not isinstance(uri, str) or not uri.strip():
            raise ValueError("uri is required")
        parsed = urlparse(uri.strip())
        if parsed.scheme not in {"https"} or not parsed.netloc:
            return LearningSource(source_id.strip(), source_type, uri.strip(), LearningSourceStatus.BLOCKED)
        return LearningSource(source_id.strip(), source_type, uri.strip(), LearningSourceStatus.QUARANTINED)

    def validate_content(self, source: LearningSource, *, content_verified: bool, security_checked: bool) -> LearningSource:
        if not isinstance(source, LearningSource):
            raise ValueError("invalid learning source")
        if source.status is LearningSourceStatus.BLOCKED:
            return source
        if not content_verified or not security_checked:
            return LearningSource(
                source.source_id, source.source_type, source.uri,
                LearningSourceStatus.QUARANTINED,
                content_verified=content_verified,
                security_checked=security_checked,
            )
        return LearningSource(
            source.source_id, source.source_type, source.uri,
            LearningSourceStatus.VALIDATED,
            content_verified=True,
            security_checked=True,
        )

    def admit_knowledge(self, source: LearningSource, *, knowledge_validated: bool) -> LearningSource:
        if not isinstance(source, LearningSource):
            raise ValueError("invalid learning source")
        if source.status is not LearningSourceStatus.VALIDATED:
            return source
        return LearningSource(
            source.source_id, source.source_type, source.uri,
            source.status,
            content_verified=source.content_verified,
            security_checked=source.security_checked,
            knowledge_validated=knowledge_validated,
            operation_eligible=False,
        )
