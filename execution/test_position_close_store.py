from execution.position_close_store import PositionCloseState, PositionCloseStore


def test_unknown_close_requires_reconciliation_before_retry(tmp_path):
    store = PositionCloseStore(tmp_path / "closes.json")
    store.begin("req-1", "ticket-1")
    store.finish("req-1", PositionCloseState.UNKNOWN, message="timeout")

    try:
        store.begin("req-1", "ticket-1")
    except ValueError as exc:
        assert "bloqueada até reconciliação" in str(exc)
    else:
        raise AssertionError("retry must be blocked before reconciliation")


def test_open_observation_allows_a_new_explicit_close_attempt(tmp_path):
    store = PositionCloseStore(tmp_path / "closes.json")
    store.begin("req-2", "ticket-2")
    store.finish("req-2", PositionCloseState.UNKNOWN, message="ambiguous")
    store.reconcile("req-2", PositionCloseState.OPEN, message="position still open")

    next_attempt = store.begin("req-2", "ticket-2")
    assert next_attempt.state is PositionCloseState.REQUESTED
    assert next_attempt.attempt == 2
    history = store.history("req-2")
    assert [record.state for record in history] == [
        PositionCloseState.OPEN,
        PositionCloseState.REQUESTED,
    ]
    reloaded = PositionCloseStore(tmp_path / "closes.json")
    assert [record.attempt for record in reloaded.history("req-2")] == [1, 2]


def test_closed_observation_is_terminal_and_cannot_be_retried(tmp_path):
    store = PositionCloseStore(tmp_path / "closes.json")
    store.begin("req-3", "ticket-3")
    store.reconcile("req-3", PositionCloseState.CLOSED, message="close deal verified")

    try:
        store.begin("req-3", "ticket-3")
    except ValueError as exc:
        assert "bloqueada até reconciliação" in str(exc)
    else:
        raise AssertionError("confirmed closed position must be terminal")



def test_legacy_accepted_close_is_recovered_as_unknown_and_requires_reconciliation(tmp_path):
    path = tmp_path / "legacy-closes.json"
    path.write_text(
        '[{"request_id":"legacy-1","external_id":"ticket-legacy",'
        '"state":"ACCEPTED","updated_at":"2026-11-05T12:00:00+00:00",'
        '"attempt":1}]',
        encoding="utf-8",
    )

    store = PositionCloseStore(path)
    recovered = store.get("legacy-1")
    assert recovered.state is PositionCloseState.UNKNOWN
    assert store.records()[0].state is PositionCloseState.UNKNOWN

    try:
        store.begin("legacy-1", "ticket-legacy")
    except ValueError as exc:
        assert "bloqueada até reconciliação" in str(exc)
    else:
        raise AssertionError("legacy ACCEPTED close must not be retried before broker reconciliation")

    store.reconcile("legacy-1", PositionCloseState.OPEN, message="broker confirms position remains open")
    retry = store.begin("legacy-1", "ticket-legacy")
    assert retry.attempt == 2
