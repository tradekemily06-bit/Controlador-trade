from pathlib import Path

from streamlit.testing.v1 import AppTest


PANEL_APP = Path(__file__).resolve().parents[1] / "streamlit_panel" / "app.py"


def _open_panel(monkeypatch):
    # Keep the test isolated from a real runtime or broker.
    monkeypatch.setenv("CONTROLADOR_API_BASE_URL", "http://127.0.0.1:1")
    monkeypatch.setenv("CONTROLADOR_REMOTE_ACCESS_REQUIRED", "false")
    monkeypatch.setenv("CONTROLADOR_LOCAL_MUTATIONS_ALLOWED", "false")
    app = AppTest.from_file(str(PANEL_APP)).run(timeout=30)
    assert not app.exception
    return app


def test_streamlit_panel_starts_and_exposes_the_expected_main_areas(monkeypatch):
    app = _open_panel(monkeypatch)
    area = next(item for item in app.radio if item.label == "Áreas principais")
    assert list(area.options) == [
        "COCKPIT",
        "ANÁLISE",
        "ESTUDO",
        "RESERVA FISCAL",
        "ASSISTENTE DO ECOSSISTEMA",
        "MAIS / ADMIN",
    ]


def test_streamlit_assistant_is_a_separate_main_area_with_explicit_consent(monkeypatch):
    app = _open_panel(monkeypatch)
    area = next(item for item in app.radio if item.label == "Áreas principais")
    area.set_value("ASSISTENTE DO ECOSSISTEMA").run(timeout=30)

    assert not app.exception
    assert any(item.value == "Assistente do Ecossistema" for item in app.subheader)
    assert any("Autorizo enviar minha pergunta" in item.label for item in app.checkbox)


def test_streamlit_fiscal_reserve_is_a_separate_main_area(monkeypatch):
    app = _open_panel(monkeypatch)
    area = next(item for item in app.radio if item.label == "Áreas principais")
    area.set_value("RESERVA FISCAL").run(timeout=30)

    assert not app.exception
    assert any(item.value == "Reserva Fiscal" for item in app.subheader)


def test_streamlit_financeiro_remains_available_under_more_admin(monkeypatch):
    app = _open_panel(monkeypatch)
    area = next(item for item in app.radio if item.label == "Áreas principais")
    area.set_value("MAIS / ADMIN").run(timeout=30)

    assert not app.exception
    module = next(item for item in app.radio if item.label == "Módulos")
    assert "Financeiro" in list(module.options)

    module.set_value("Financeiro").run(timeout=30)
    assert not app.exception
    assert any(item.value == "Financeiro" for item in app.subheader)



def test_kill_switch_panel_requires_reason_and_explicit_confirmation(monkeypatch):
    app = _open_panel(monkeypatch)
    area = next(item for item in app.radio if item.label == "Áreas principais")
    area.set_value("MAIS / ADMIN").run(timeout=30)
    module = next(item for item in app.radio if item.label == "Módulos")
    assert "Kill Switch" in list(module.options)
    module.set_value("Kill Switch").run(timeout=30)

    assert not app.exception
    assert any(item.value == "Proteção operacional · Kill Switch" for item in app.subheader)
    assert any(item.label == "Motivo obrigatório da ativação" for item in app.text_input)
    assert any(
        item.label == "Confirmo que quero bloquear novas execuções neste runtime."
        for item in app.checkbox
    )
    assert any(item.label == "Ativar Kill Switch" for item in app.button)
