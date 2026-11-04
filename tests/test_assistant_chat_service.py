from __future__ import annotations

import assistant.chat_service as chat_module
from assistant.chat_service import AssistantUnavailableError, EcosystemAssistant


class FakeStore:
    def __init__(self, history=None):
        self.messages = []
        self._history = list(history or [])

    def append(self, identity, conversation_id, role, content):
        self.messages.append((identity, conversation_id, role, content))
        return conversation_id or "conversation-test"

    def history(self, identity, conversation_id, limit):
        return self._history[-limit:] + [
            {"role": role, "content": content}
            for _identity, _cid, role, content in self.messages
            if role == "user"
        ]

    def list(self, identity):
        return []

    def delete(self, identity, conversation_id):
        return True


class FakeCompletion:
    def __init__(self, answer="Resposta de teste"):
        self.answer = answer
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return type(
            "Response",
            (),
            {
                "choices": [
                    type(
                        "Choice",
                        (),
                        {"message": type("Message", (), {"content": self.answer})()},
                    )()
                ]
            },
        )()


class FakeClient:
    def __init__(self, completion):
        self.chat = type(
            "Chat",
            (),
            {"completions": completion},
        )()


def _assistant(store, completion, monkeypatch):
    monkeypatch.setattr(
        chat_module,
        "collect_read_only_context",
        lambda *args, **kwargs: {
            "execution": {"allowed": False, "real": "DISABLED"},
            "fiscal": {"reserve_calculated": False},
            "private_free_text": "must not be added by this test fixture",
        },
    )
    return EcosystemAssistant(
        store=store,
        service=object(),
        fiscal=object(),
        client_factory=lambda: FakeClient(completion),
        model="fake-model",
    )


def test_readiness_never_claims_provider_connection_was_tested():
    assistant = EcosystemAssistant(
        store=FakeStore(),
        service=object(),
        fiscal=object(),
        client_factory=lambda: object(),
        model="fake-model",
    )

    status = assistant.readiness()

    assert status["available"] is True
    assert status["credentials_configured"] is True
    assert status["client_initialized"] is True
    assert status["connection_tested"] is False
    assert status["status"] == "CONFIGURED_NOT_TESTED"
    assert status["may_execute_orders"] is False
    assert status["may_enable_real"] is False
    assert status["may_move_money"] is False


def test_ask_uses_read_only_system_rules_bounded_history_and_no_execution(monkeypatch):
    store = FakeStore(
        history=[
            {"role": "user", "content": "pergunta anterior"},
            {"role": "assistant", "content": "resposta anterior"},
        ]
    )
    completion = FakeCompletion()
    assistant = _assistant(store, completion, monkeypatch)

    result = assistant.ask(
        identity="single:owner",
        message="Explique o resumo fiscal",
        fiscal_owner_id="single:owner",
    )

    sent = completion.calls[0]["messages"]
    assert sent[0]["role"] == "system"
    assert "Somente leitura" in sent[0]["content"]
    assert "não envia ordens" in sent[0]["content"]
    assert "não ativa REAL" in sent[0]["content"]
    assert sent[1]["role"] == "user"
    assert "BLOCO DE DADOS DO ECOSSISTEMA" in sent[1]["content"]
    assert sent[1]["content"].find('"execution"') >= 0
    assert sent[-1] == {"role": "user", "content": "Explique o resumo fiscal"}
    assert completion.calls[0]["model"] == "fake-model"
    assert completion.calls[0]["max_completion_tokens"] == 600
    assert result["read_only"] is True
    assert result["execution_allowed"] is False
    assert result["may_execute_orders"] is False
    assert result["may_enable_real"] is False
    assert result["may_move_money"] is False
    assert store.messages[-1] == (
        "single:owner",
        "conversation-test",
        "assistant",
        "Resposta de teste",
    )


def test_ask_provider_error_is_sanitized_and_user_message_remains_in_history(monkeypatch):
    class FailingCompletion:
        def create(self, **kwargs):
            raise RuntimeError("secret-provider-detail OPENAI_API_KEY=should-never-leak")

    store = FakeStore()
    assistant = _assistant(store, FailingCompletion(), monkeypatch)

    try:
        assistant.ask(
            identity="single:owner",
            message="Minha pergunta",
            fiscal_owner_id="single:owner",
        )
    except AssistantUnavailableError as exc:
        assert str(exc) == (
            "Não foi possível obter resposta agora; sua mensagem ficou no histórico."
        )
        assert "secret-provider-detail" not in str(exc)
        assert "OPENAI_API_KEY" not in str(exc)
    else:
        raise AssertionError("provider errors must be returned as a sanitized failure")

    assert store.messages == [
        ("single:owner", None, "user", "Minha pergunta")
    ]
