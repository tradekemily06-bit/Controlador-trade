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
