from pathlib import Path


HTML = Path(__file__).with_name("assistant.html").read_text(encoding="utf-8")


def test_standalone_assistant_checks_provider_readiness_before_enabling_chat():
    assert 'api("/api/assistant/status")' in HTML
    assert "async function checkReadiness()" in HTML
    assert '$("message").disabled=!assistantConfigured' in HTML
    assert '$("send").disabled=!assistantConfigured' in HTML
    assert "Credenciais configuradas; conexão ainda não testada." in HTML


def test_standalone_assistant_never_submits_when_provider_is_not_configured():
    assert "if(!assistantConfigured)return" in HTML
    assert 'api("/api/assistant/chat"' in HTML
    assert "Não foi possível verificar a configuração do Assistente." in HTML
