from __future__ import annotations

import pytest

from assistant.conversation_store import AssistantConversationStore


def test_conversation_store_isolates_list_history_append_and_delete_by_owner(tmp_path):
    store = AssistantConversationStore(tmp_path / "assistant.sqlite3")
    conversation_id = store.append("owner-a", None, "user", "Mensagem privada")

    assert len(store.list("owner-a")) == 1
    assert store.list("owner-b") == []
    with pytest.raises(PermissionError):
        store.history("owner-b", conversation_id)
    with pytest.raises(PermissionError):
        store.append("owner-b", conversation_id, "assistant", "Tentativa")
    with pytest.raises(PermissionError):
        store.delete("owner-b", conversation_id)

    assert [item["content"] for item in store.history("owner-a", conversation_id)] == [
        "Mensagem privada"
    ]


def test_delete_removes_messages_and_conversation_only_for_owner(tmp_path):
    store = AssistantConversationStore(tmp_path / "assistant.sqlite3")
    first = store.append("owner-a", None, "user", "Primeira conversa")
    second = store.append("owner-a", None, "user", "Segunda conversa")

    assert store.delete("owner-a", first) is True
    assert [item["conversation_id"] for item in store.list("owner-a")] == [second]
    with pytest.raises(PermissionError):
        store.history("owner-a", first)
    assert [item["content"] for item in store.history("owner-a", second)] == [
        "Segunda conversa"
    ]


@pytest.mark.parametrize("identity", [None, "", "   ", 123, True, object()])
def test_owner_identity_must_be_nonempty_text(tmp_path, identity):
    store = AssistantConversationStore(tmp_path / "assistant.sqlite3")

    with pytest.raises(ValueError, match="identidade inválida"):
        store.list(identity)


@pytest.mark.parametrize("conversation_id", [123, True, [], {}, " " , "x" * 81])
def test_conversation_store_rejects_invalid_conversation_ids(tmp_path, conversation_id):
    store = AssistantConversationStore(tmp_path / "assistant.sqlite3")
    with pytest.raises(ValueError, match="identificador de conversa inválido"):
        store.history("owner-a", conversation_id)
    with pytest.raises(ValueError, match="identificador de conversa inválido"):
        store.delete("owner-a", conversation_id)


@pytest.mark.parametrize("limit", [0, 51, True, 2.5, "10", None])
def test_conversation_history_rejects_coerced_or_out_of_range_limits(tmp_path, limit):
    store = AssistantConversationStore(tmp_path / "assistant.sqlite3")
    conversation_id = store.append("owner-a", None, "user", "Mensagem")
    with pytest.raises(ValueError, match="limite de histórico inválido"):
        store.history("owner-a", conversation_id, limit=limit)


@pytest.mark.parametrize(
    ("role", "content"),
    [
        (["user"], "Mensagem"),
        ("system", "Mensagem"),
        ("user", ["Mensagem"]),
        ("assistant", ""),
        ("assistant", None),
    ],
)
def test_conversation_store_rejects_invalid_message_types(tmp_path, role, content):
    store = AssistantConversationStore(tmp_path / "assistant.sqlite3")
    with pytest.raises(ValueError, match="mensagem inválida"):
        store.append("owner-a", None, role, content)
    assert store.list("owner-a") == []
