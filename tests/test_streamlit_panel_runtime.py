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
        "FINANCEIRO",
        "RESERVA FISCAL",
        "ASSISTENTE DO ECOSSISTEMA",
        "CENTRAL",
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



def test_streamlit_fiscal_mutation_forms_stay_hidden_when_summary_is_unavailable(monkeypatch):
    app = _open_panel(monkeypatch)
    area = next(item for item in app.radio if item.label == "Áreas principais")
    area.set_value("RESERVA FISCAL").run(timeout=30)

    assert not app.exception
    assert any(
        "Resumo fiscal indisponível" in item.value
        or "Resumo fiscal incompleto ou inválido" in item.value
        for item in app.error
    )
    # No fiscal form may be rendered from an unavailable or unvalidated snapshot.
    visible_inputs = {item.label for item in app.text_input}
    assert "Ativo / instrumento negociado" not in visible_inputs
    assert "Referência / comprovante" not in visible_inputs
    assert "Referência / comprovante · Brasil" not in visible_inputs


def test_streamlit_assistant_consent_is_disabled_without_owner_identity(monkeypatch):
    monkeypatch.delenv("CONTROLADOR_SINGLE_USER_IDENTITY", raising=False)
    app = _open_panel(monkeypatch)
    area = next(item for item in app.radio if item.label == "Áreas principais")
    area.set_value("ASSISTENTE DO ECOSSISTEMA").run(timeout=30)

    consent = next(item for item in app.checkbox if "Autorizo enviar minha pergunta" in item.label)
    assert consent.disabled is True
    assert not app.exception


def test_streamlit_financeiro_has_its_own_main_area(monkeypatch):
    app = _open_panel(monkeypatch)
    area = next(item for item in app.radio if item.label == "Áreas principais")
    area.set_value("FINANCEIRO").run(timeout=30)

    assert not app.exception
    assert not any(item.label == "Módulos" for item in app.radio)
    assert any(item.value == "Financeiro" for item in app.subheader)



def test_kill_switch_panel_requires_reason_and_explicit_confirmation(monkeypatch):
    app = _open_panel(monkeypatch)
    area = next(item for item in app.radio if item.label == "Áreas principais")
    area.set_value("CENTRAL").run(timeout=30)
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



def test_all_streamlit_module_destinations_render_without_uncaught_exceptions(monkeypatch):
    app = _open_panel(monkeypatch)
    for area_name in ("COCKPIT", "ANÁLISE", "ESTUDO", "FINANCEIRO", "RESERVA FISCAL", "ASSISTENTE DO ECOSSISTEMA", "CENTRAL"):
        area = next(item for item in app.radio if item.label == "Áreas principais")
        area.set_value(area_name).run(timeout=30)
        assert not app.exception, f"area failed to render: {area_name}"

        if area_name in {"FINANCEIRO", "RESERVA FISCAL", "ASSISTENTE DO ECOSSISTEMA"}:
            expected_heading = {
                "FINANCEIRO": "Financeiro",
                "RESERVA FISCAL": "Reserva Fiscal",
                "ASSISTENTE DO ECOSSISTEMA": "Assistente do Ecossistema",
            }[area_name]
            assert any(item.value == expected_heading for item in app.subheader), f"dedicated area failed to render: {area_name}"
            continue

        module = next(item for item in app.radio if item.label == "Módulos")
        for module_name in list(module.options):
            module = next(item for item in app.radio if item.label == "Módulos")
            module.set_value(module_name).run(timeout=30)
            assert not app.exception, f"module failed to render: {area_name} / {module_name}"
            assert not any("ainda não possui integração operacional" in item.value.lower() for item in app.info), f"placeholder module: {area_name} / {module_name}"
