from pathlib import Path

from streamlit.testing.v1 import AppTest


PANEL_APP = Path(__file__).resolve().parents[1] / "streamlit_panel" / "app.py"


def _open_admin_area(monkeypatch):
    # Force fast, deterministic connection failures instead of touching a real runtime.
    monkeypatch.setenv("CONTROLADOR_API_BASE_URL", "http://127.0.0.1:1")
    monkeypatch.setenv("CONTROLADOR_REMOTE_ACCESS_REQUIRED", "false")
    app = AppTest.from_file(str(PANEL_APP)).run(timeout=20)
    assert not app.exception
    area = next(item for item in app.radio if item.label == "Áreas principais")
    area.set_value("MAIS / ADMIN").run(timeout=20)
    assert not app.exception
    return app


def test_streamlit_panel_runs_and_exposes_all_reference_navigation_areas(monkeypatch):
    monkeypatch.setenv("CONTROLADOR_API_BASE_URL", "http://127.0.0.1:1")
    monkeypatch.setenv("CONTROLADOR_REMOTE_ACCESS_REQUIRED", "false")
    app = AppTest.from_file(str(PANEL_APP)).run(timeout=20)

    assert not app.exception
    area = next(item for item in app.radio if item.label == "Áreas principais")
    assert list(area.options) == ["COCKPIT", "ANÁLISE", "ESTUDO", "MAIS / ADMIN"]


def test_streamlit_admin_area_renders_fiscal_reserve_and_assistant_modules(monkeypatch):
    app = _open_admin_area(monkeypatch)
    module = next(item for item in app.radio if item.label == "Módulos")
    assert "Reserva Fiscal" in list(module.options)
    assert "Assistente do Ecossistema" in list(module.options)

    module.set_value("Assistente do Ecossistema").run(timeout=20)
    assert not app.exception
    assert any(item.value == "Assistente do Ecossistema" for item in app.subheader)
    assert any("Autorizo enviar minha pergunta" in item.label for item in app.checkbox)


def test_streamlit_fiscal_reserve_module_reaches_the_real_screen(monkeypatch):
    app = _open_admin_area(monkeypatch)
    module = next(item for item in app.radio if item.label == "Módulos")
    module.set_value("Reserva Fiscal").run(timeout=20)

    assert not app.exception
    assert any(item.value == "Reserva Fiscal" for item in app.subheader)
