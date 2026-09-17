from __future__ import annotations


def test_app_run_uses_selected_port(monkeypatch):
    import app

    calls: dict[str, object] = {}

    class FakeServer:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def serve_forever(self):
            calls["served"] = True

    def fake_make_server(host, port, application):
        calls.update(host=host, port=port, application=application)
        return FakeServer()

    monkeypatch.setenv("CONTROLADOR_HOST", "127.0.0.1")
    monkeypatch.setenv("PORT", "8765")
    monkeypatch.setattr(app, "make_server", fake_make_server)

    app.run()

    assert calls["host"] == "127.0.0.1"
    assert calls["port"] == 8765
    assert calls["application"] is app.application
    assert calls["served"] is True
