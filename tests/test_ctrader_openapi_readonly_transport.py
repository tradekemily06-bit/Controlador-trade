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


def _reconnect_test_transport(is_live=False):
    from threading import Event, Lock

    class Request:
        def __init__(self):
            self.ctidTraderAccountId = None
            self.symbolId = []
            self.subscribeToSpotTimestamp = False
            self.period = None

    class Period:
        @staticmethod
        def Value(value):
            return {"M5": 5}[value]

    transport = object.__new__(CTraderOpenApiReadOnlyTransport)
    transport._reconnect_lock = Lock()
    transport._account_id = 77
    transport._account_authenticated = False
    transport._connected = Event()
    transport._disconnected = Event()
    transport._client = None
    transport._timeout = 5
    transport._spot_callbacks = {9001: lambda _event: None}
    transport._trendbar_callbacks = {(9001, "M5"): lambda _event: None}
    transport._trendbar_spot_only = {9001}
    transport._messages = {"subscribe_spots": Request, "subscribe_trendbars": Request}
    transport._period_enum = Period
    transport.steps = []
    def connect():
        transport.steps.append("connect")
        transport._connected.set()
    def application_auth():
        transport.steps.append("application_auth")
    def account_details(account_id):
        transport.steps.append("account_details")
        return {"account_id": account_id, "is_live": is_live}
    def account_auth(account_id):
        transport.steps.append("account_auth")
        transport._account_authenticated = True
    def send(request):
        transport.steps.append("subscribe_spots" if request.symbolId and isinstance(request.symbolId, list) else "subscribe_trendbars")
    transport.connect = connect
    transport.application_auth = application_auth
    transport.account_details = account_details
    transport.account_auth = account_auth
    transport._start_spot_worker = lambda: transport.steps.append("worker")
    transport._send = send
    return transport


def test_reconnect_reauthenticates_demo_and_restores_spot_before_trendbars():
    transport = _reconnect_test_transport(is_live=False)
    result = transport.reconnect()
    assert result == {"account_id": 77, "is_live": False}
    assert transport._account_authenticated is True
    assert transport.steps[:4] == ["connect", "application_auth", "account_details", "account_auth"]
    assert transport.steps[4:] == ["worker", "subscribe_spots", "subscribe_trendbars"]
    assert set(transport._spot_callbacks) == {9001}
    assert set(transport._trendbar_callbacks) == {(9001, "M5")}


def test_reconnect_refuses_real_account_and_keeps_session_unhealthy():
    transport = _reconnect_test_transport(is_live=True)
    with pytest.raises(PermissionError, match="não é DEMO"):
        transport.reconnect()
    assert transport._account_authenticated is False
    assert transport._connected.is_set() is False
    assert set(transport._spot_callbacks) == {9001}
    assert set(transport._trendbar_callbacks) == {(9001, "M5")}


def test_list_accounts_returns_only_safe_ids_and_mode_flags():
    from types import SimpleNamespace

    class Request:
        def __init__(self): self.accessToken = None

    transport = object.__new__(CTraderOpenApiReadOnlyTransport)
    transport._messages = {"account_list": Request}
    transport._access_token = "server-side-token"
    sent = []
    transport._send = lambda request: (
        sent.append(request) or SimpleNamespace(ctidTraderAccount=[
            SimpleNamespace(ctidTraderAccountId=123, isLive=False),
            SimpleNamespace(ctidTraderAccountId=456, isLive=True),
        ])
    )
    result = transport.list_accounts()
    assert result == (
        {"account_id": 123, "is_live": False},
        {"account_id": 456, "is_live": True},
    )
    assert sent[0].accessToken == "server-side-token"


def test_list_accounts_rejects_unconfirmed_account_mode():
    from types import SimpleNamespace

    class Request:
        def __init__(self): self.accessToken = None

    transport = object.__new__(CTraderOpenApiReadOnlyTransport)
    transport._messages = {"account_list": Request}
    transport._access_token = "server-side-token"
    transport._send = lambda _request: SimpleNamespace(ctidTraderAccount=[
        SimpleNamespace(ctidTraderAccountId=123, isLive=None),
    ])
    with pytest.raises(PermissionError, match="sem confirmação"):
        transport.list_accounts()
