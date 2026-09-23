from execution.external_execution_registry import ExternalExecutionRegistry


def test_external_id_cannot_be_reused_by_another_request(tmp_path):
    registry = ExternalExecutionRegistry(tmp_path / "external.json")
    registry.bind("req-1", "broker-a", "ext-1")
    try:
        registry.bind("req-2", "broker-a", "ext-1")
    except ValueError as exc:
        assert "external_id" in str(exc)
    else:
        raise AssertionError("external_id must be unique per broker")


def test_same_binding_is_idempotent(tmp_path):
    registry = ExternalExecutionRegistry(tmp_path / "external.json")
    registry.bind("req-1", "broker-a", "ext-1")
    registry.bind("req-1", "broker-a", "ext-1")
    assert registry.get("req-1") == ("broker-a", "ext-1")
