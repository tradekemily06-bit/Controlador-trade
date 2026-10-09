from __future__ import annotations

from http.client import HTTPConnection
from threading import Event, Thread
from time import monotonic
from urllib.request import urlopen

from wsgiref.simple_server import make_server

from app import ThreadingWSGIServer


def test_slow_request_does_not_block_health_like_request():
    slow_started = Event()
    release_slow = Event()

    def application(environ, start_response):
        if environ.get("PATH_INFO") == "/slow":
            slow_started.set()
            release_slow.wait(timeout=3)
            body = b"slow"
        else:
            body = b"fast"
        start_response("200 OK", [("Content-Type", "text/plain"), ("Content-Length", str(len(body)))])
        return [body]

    server = make_server("127.0.0.1", 0, application, server_class=ThreadingWSGIServer)
    server_thread = Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    host, port = server.server_address

    def request_slow():
        connection = HTTPConnection(host, port, timeout=4)
        try:
            connection.request("GET", "/slow")
            response = connection.getresponse()
            response.read()
        finally:
            connection.close()

    slow_thread = Thread(target=request_slow, daemon=True)
    try:
        slow_thread.start()
        assert slow_started.wait(timeout=1), "slow request did not start"

        started = monotonic()
        with urlopen(f"http://{host}:{port}/health", timeout=1.5) as response:
            assert response.status == 200
            assert response.read() == b"fast"
        assert monotonic() - started < 1.5, "health-like request waited behind the slow request"
    finally:
        release_slow.set()
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=2)
        slow_thread.join(timeout=2)
