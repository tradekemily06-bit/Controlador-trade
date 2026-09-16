from app import _learning_source_for_request


def test_learning_http_source_lookup_uses_service_scoped_view(monkeypatch):
    class FakeService:
        def learning_sources_view(self):
            return [
                {
                    "source_id": "tenant-a-source",
                    "source_type": "LINK",
                    "uri": "https://example.com/a",
                    "status": "VALIDATED",
                    "content_verified": True,
                    "security_checked": True,
                    "knowledge_validated": True,
                    "operation_eligible": False,
                }
            ]

    import app

    monkeypatch.setattr(app, "SERVICE", FakeService())
    source = _learning_source_for_request("tenant-a-source")

    assert source.source_id == "tenant-a-source"
    assert source.status.value == "VALIDATED"
    assert source.knowledge_validated is True
    assert source.operation_eligible is False


def test_learning_http_source_lookup_does_not_accept_missing_source(monkeypatch):
    class FakeService:
        def learning_sources_view(self):
            return []

    import app

    monkeypatch.setattr(app, "SERVICE", FakeService())

    import pytest
    with pytest.raises(ValueError, match="source_id não encontrado"):
        _learning_source_for_request("missing")
