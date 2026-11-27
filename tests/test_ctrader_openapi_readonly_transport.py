from __future__ import annotations

import builtins

import pytest

from integration.ctrader_openapi_readonly_transport import (
    CTraderOpenApiReadOnlyTransport,
)


def test_official_sdk_is_loaded_lazily_and_missing_dependency_fails_closed(monkeypatch):
    original_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name == "ctrader_open_api" or name.startswith("ctrader_open_api."):
            raise ImportError("blocked by test")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    with pytest.raises(RuntimeError, match="SDK oficial ausente"):
        CTraderOpenApiReadOnlyTransport(
            client_id="test-client",
            client_secret="test-secret",
            access_token="test-token",
        )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"client_id": "", "client_secret": "secret", "access_token": "token"},
        {"client_id": "client", "client_secret": "", "access_token": "token"},
        {"client_id": "client", "client_secret": "secret", "access_token": ""},
    ],
)
def test_transport_rejects_missing_server_side_credentials(kwargs):
    with pytest.raises(ValueError):
        CTraderOpenApiReadOnlyTransport(**kwargs)


def test_transport_rejects_unsafe_timeout_before_loading_sdk():
    with pytest.raises(ValueError, match="timeout_seconds"):
        CTraderOpenApiReadOnlyTransport(
            client_id="client",
            client_secret="secret",
            access_token="token",
            timeout_seconds=1,
        )



def test_spot_subscription_is_account_scoped_and_uses_timestamp():
    from threading import Event, RLock
    import queue

    class Request:
        def __init__(self):
            self.ctidTraderAccountId = None
            self.symbolId = []
            self.subscribeToSpotTimestamp = False

    transport = object.__new__(CTraderOpenApiReadOnlyTransport)
    transport._account_authenticated = True
    transport._account_id = 77
    transport._messages = {"subscribe_spots": Request, "unsubscribe_spots": Request}
    transport._lock = RLock()
    transport._spot_callbacks = {}
    transport._spot_queue = queue.Queue(maxsize=2048)
    transport._spot_worker = None
    transport._spot_worker_stop = Event()
    transport._spot_overflow_count = 0
    transport._start_spot_worker = lambda: None
    sent = []
    transport._send = sent.append
    callback = lambda _event: None

    transport.subscribe_spots(77, 9001, callback)
    request = sent.pop()
    assert request.ctidTraderAccountId == 77
    assert list(request.symbolId) == [9001]
    assert request.subscribeToSpotTimestamp is True
    assert transport._spot_callbacks[9001] is callback

    transport.unsubscribe_spots(77, 9001)
    request = sent.pop()
    assert request.ctidTraderAccountId == 77
    assert list(request.symbolId) == [9001]
    assert 9001 not in transport._spot_callbacks


def test_spot_subscription_rejects_other_account_and_duplicate_symbol():
    from threading import Event, RLock
    import queue

    class Request:
        def __init__(self):
            self.symbolId = []

    transport = object.__new__(CTraderOpenApiReadOnlyTransport)
    transport._account_authenticated = True
    transport._account_id = 77
    transport._messages = {"subscribe_spots": Request}
    transport._lock = RLock()
    transport._spot_callbacks = {9001: lambda _event: None}
    transport._spot_queue = queue.Queue(maxsize=2048)
    transport._spot_worker = None
    transport._spot_worker_stop = Event()
    transport._spot_overflow_count = 0
    transport._start_spot_worker = lambda: None
    transport._send = lambda _request: None

    with pytest.raises(PermissionError):
        transport.subscribe_spots(88, 9002, lambda _event: None)
    with pytest.raises(ValueError, match="já existe"):
        transport.subscribe_spots(77, 9001, lambda _event: None)



def test_live_trendbar_subscription_sends_spots_first_and_uses_period():
    from threading import Event, RLock
    import queue

    class Request:
        def __init__(self):
            self.ctidTraderAccountId = None
            self.symbolId = []
            self.period = None
            self.subscribeToSpotTimestamp = False

    class Period:
        @staticmethod
        def Value(value):
            return {"M1": 1, "M5": 5}[value]

    transport = object.__new__(CTraderOpenApiReadOnlyTransport)
    transport._account_authenticated = True
    transport._account_id = 77
    transport._messages = {
        "subscribe_spots": Request,
        "subscribe_trendbars": Request,
    }
    transport._period_enum = Period
    transport._lock = RLock()
    transport._spot_callbacks = {}
    transport._trendbar_callbacks = {}
    transport._trendbar_spot_only = set()
    transport._spot_queue = queue.Queue(maxsize=2048)
    transport._spot_worker = None
    transport._spot_worker_stop = Event()
    transport._spot_overflow_count = 0
    transport._start_spot_worker = lambda: None
    sent = []
    transport._send = sent.append

    transport.subscribe_live_trendbars(77, 9001, "M5", lambda _event: None)

    assert len(sent) == 2
    spot_request, trendbar_request = sent
    assert spot_request.ctidTraderAccountId == 77
    assert list(spot_request.symbolId) == [9001]
    assert spot_request.subscribeToSpotTimestamp is True
    assert trendbar_request.ctidTraderAccountId == 77
    assert trendbar_request.symbolId == 9001
    assert trendbar_request.period == 5
    assert (9001, "M5") in transport._trendbar_callbacks


def test_live_trendbar_subscription_rejects_duplicate_and_other_account():
    from threading import Event, RLock
    import queue

    transport = object.__new__(CTraderOpenApiReadOnlyTransport)
    transport._account_authenticated = True
    transport._account_id = 77
    transport._trendbar_callbacks = {(9001, "M5"): lambda _event: None}
    transport._trendbar_spot_only = set()
    transport._spot_callbacks = {}
    transport._lock = RLock()
    transport._spot_queue = queue.Queue(maxsize=2048)
    transport._spot_worker = None
    transport._spot_worker_stop = Event()
    transport._spot_overflow_count = 0

    with pytest.raises(PermissionError):
        transport.subscribe_live_trendbars(88, 9002, "M5", lambda _event: None)
    with pytest.raises(ValueError, match="já existe"):
        transport.subscribe_live_trendbars(77, 9001, "M5", lambda _event: None)


def test_last_live_trendbar_unsubscribes_its_internal_spot_carrier():
    from threading import Event, RLock
    import queue

    class Request:
        def __init__(self):
            self.ctidTraderAccountId = None
            self.symbolId = []
            self.period = None

    class Period:
        @staticmethod
        def Value(value):
            return {"M5": 5}[value]

    transport = object.__new__(CTraderOpenApiReadOnlyTransport)
    transport._account_authenticated = True
    transport._account_id = 77
    transport._messages = {
        "subscribe_spots": Request,
        "unsubscribe_spots": Request,
        "subscribe_trendbars": Request,
        "unsubscribe_trendbars": Request,
    }
    transport._period_enum = Period
    transport._lock = RLock()
    transport._spot_callbacks = {}
    transport._trendbar_callbacks = {}
    transport._trendbar_spot_only = set()
    transport._spot_queue = queue.Queue(maxsize=2048)
    transport._spot_worker = None
    transport._spot_worker_stop = Event()
    transport._spot_overflow_count = 0
    transport._start_spot_worker = lambda: None
    sent = []
    transport._send = sent.append

    transport.subscribe_live_trendbars(77, 9001, "M5", lambda _event: None)
    assert 9001 in transport._trendbar_spot_only
    sent.clear()
    transport.unsubscribe_live_trendbars(77, 9001, "M5")

    assert len(sent) == 2
    assert sent[0].period == 5
    assert list(sent[1].symbolId) == [9001]
    assert 9001 not in transport._spot_callbacks
    assert 9001 not in transport._trendbar_spot_only
