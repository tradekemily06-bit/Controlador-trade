import pytest

from assistant.tenant_read_only_context import collect_tenant_fiscal_context
from finance.tenant_fiscal_store import TenantFiscalStoreFactory
from security.tenant_context import TenantContext


def test_tenant_fiscal_context_resolves_only_the_requested_owner(tmp_path):
    factory = TenantFiscalStoreFactory(tmp_path)
    alice_identity = TenantContext("tenant-a", "alice")
    bob_identity = TenantContext("tenant-a", "bob")

    alice_context = collect_tenant_fiscal_context(factory, alice_identity)
    bob_context = collect_tenant_fiscal_context(factory, bob_identity)
    alice_repositories = factory.get(alice_identity)
    bob_repositories = factory.get(bob_identity)

    assert alice_repositories.owner_id != bob_repositories.owner_id
    assert alice_repositories.database_path != bob_repositories.database_path
    for context in (alice_context, bob_context):
        assert context["scope"] == "TENANT_AND_SUBJECT"
        assert context["operational_context"] == "NOT_INCLUDED_SHARED_STATE"
        assert "system" not in context
        assert "risk" not in context
        assert "operations" not in context
        assert "statistics" not in context
        assert "recent_decisions" not in context
        assert "fiscal_reserve" in context
        assert context["assistant_safety"]["read_only"] is True
        assert context["assistant_safety"]["may_execute_orders"] is False


def test_tenant_fiscal_context_rejects_caller_supplied_repositories_and_identity():
    factory = TenantFiscalStoreFactory(".")
    with pytest.raises(TypeError):
        collect_tenant_fiscal_context({"get": lambda _: None}, TenantContext("tenant-a", "alice"))
    with pytest.raises(TypeError):
        collect_tenant_fiscal_context(factory, {"tenant_id": "tenant-a", "subject_id": "alice"})


def test_tenant_assistant_chat_uses_only_tenant_context_and_tenant_owned_history(monkeypatch):
    from assistant.chat_service import EcosystemAssistant
    from security.tenant_context import TenantContext

    class Store:
        def __init__(self):
            self.items = []
        def append(self, identity, cid, role, content):
            self.items.append((identity, cid, role, content))
            return cid or "tenant-conversation"
        def history(self, identity, cid, limit):
            assert identity == "tenant:tenant-a:subject:alice"
            return [
                {"role": role, "content": content}
                for owner, _cid, role, content in self.items
                if owner == identity
            ][-limit:]

    class Completion:
        def __init__(self):
            self.calls = []
        def create(self, **kwargs):
            self.calls.append(kwargs)
            return type(
                "Response", (), {
                    "choices": [type(
                        "Choice", (), {
                            "message": type("Message", (), {"content": "Resposta isolada"})()
                        }
                    )()]
                }
            )()

    completion = Completion()
    store = Store()
    assistant = EcosystemAssistant(
        store=store,
        service=object(),
        fiscal=object(),
        client_factory=lambda: type(
            "Client", (), {
                "chat": type("Chat", (), {
                    "completions": completion
                })()
            }
        )(),
        model="test-model",
    )
    identity = TenantContext("tenant-a", "alice")
    factory = object()
    isolated_context = {
        "scope": "TENANT_AND_SUBJECT",
        "fiscal_reserve": {"total": 0},
        "assistant_safety": {"read_only": True, "may_execute_orders": False},
    }
    import assistant.tenant_read_only_context as tenant_context_module
    monkeypatch.setattr(
        tenant_context_module,
        "collect_tenant_fiscal_context",
        lambda received_factory, received_identity: (
            isolated_context
            if received_factory is factory and received_identity is identity
            else (_ for _ in ()).throw(AssertionError("tenant boundary changed"))
        ),
    )

    result = assistant.ask_tenant(identity, factory, "Qual é minha reserva?")

    assert result["scope"] == "TENANT_AND_SUBJECT"
    assert result["execution_allowed"] is False
    assert result["may_execute_orders"] is False
    assert store.items[0][0] == identity.key
    assert store.items[-1][0] == identity.key
    assert "fiscal_reserve" in completion.calls[0]["messages"][1]["content"]
    assert "shared_intelligence" not in completion.calls[0]["messages"][1]["content"]
    assert "EcosystemService" not in completion.calls[0]["messages"][1]["content"]


def test_tenant_assistant_chat_rejects_untrusted_identity_before_persisting():
    from assistant.chat_service import EcosystemAssistant

    class Store:
        def append(self, *args):
            raise AssertionError("mensagem não pode ser persistida")
        def history(self, *args):
            raise AssertionError("histórico não pode ser lido")

    assistant = EcosystemAssistant(
        store=Store(), service=object(), fiscal=object(),
        client_factory=lambda: object(), model="test-model",
    )
    with pytest.raises(TypeError):
        assistant.ask_tenant({"tenant_id": "tenant-a", "subject_id": "alice"}, object(), "Olá")
