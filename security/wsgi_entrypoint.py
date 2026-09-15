"""Production WSGI entrypoint that guarantees request identity cleanup."""
from __future__ import annotations

import os
from wsgiref.simple_server import make_server

from app import application as _application
from security.http_identity import clear_trusted_identity


def application(environ, start_response):
    """Run the application with fail-safe trusted-identity cleanup."""
    try:
        return _application(environ, start_response)
    finally:
        clear_trusted_identity()


def run() -> None:
    host = os.environ.get("CONTROLADOR_HOST", "0.0.0.0")
    selected_port = int(os.environ.get("PORT", "7860"))
    with make_server(host, selected_port, application) as server:
        server.serve_forever()


if __name__ == "__main__":
    run()
