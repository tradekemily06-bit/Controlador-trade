from __future__ import annotations

import hashlib
import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path


class AssistantConversationStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._db() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS conversations("
                "id TEXT PRIMARY KEY, owner TEXT NOT NULL, title TEXT NOT NULL, "
                "updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
            )
            db.execute(
                "CREATE TABLE IF NOT EXISTS messages("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, conversation_id TEXT NOT NULL, "
                "role TEXT NOT NULL CHECK(role IN ('user','assistant')), "
                "content TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
            )
            db.execute(
                "CREATE INDEX IF NOT EXISTS conversations_owner "
                "ON conversations(owner,updated_at DESC)"
            )

    @contextmanager
    def _db(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout = 10000")
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def _owner(identity):
        if not isinstance(identity, str):
            raise ValueError("identidade inválida")
        value = identity.strip().casefold()
        if not value:
            raise ValueError("identidade inválida")
        return hashlib.sha256(value.encode()).hexdigest()

    @staticmethod
    def _conversation_id(value, *, optional=False):
        if optional and value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("identificador de conversa inválido")
        normalized = value.strip()
        if optional and not normalized:
            return None
        if not normalized or len(normalized) > 80:
            raise ValueError("identificador de conversa inválido")
        return normalized

    @staticmethod
    def _history_limit(value):
        if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 50:
            raise ValueError("limite de histórico inválido")
        return value

    @staticmethod
    def _message(role, content):
        if not isinstance(role, str) or role not in ("user", "assistant"):
            raise ValueError("mensagem inválida")
        if not isinstance(content, str) or not content.strip():
            raise ValueError("mensagem inválida")
        return role, content.strip()

    def list(self, identity):
        owner = self._owner(identity)
        with self._db() as db:
            return [
                dict(row)
                for row in db.execute(
                    "SELECT id AS conversation_id,title,updated_at "
                    "FROM conversations WHERE owner=? ORDER BY updated_at DESC LIMIT 30",
                    (owner,),
                )
            ]

    def history(self, identity, cid, limit=30):
        owner = self._owner(identity)
        conversation_id = self._conversation_id(cid)
        history_limit = self._history_limit(limit)
        with self._db() as db:
            exists = db.execute(
                "SELECT 1 FROM conversations WHERE id=? AND owner=?",
                (conversation_id, owner),
            ).fetchone()
            if not exists:
                raise PermissionError("conversa não encontrada")
            rows = db.execute(
                "SELECT role,content,created_at FROM messages "
                "WHERE conversation_id=? ORDER BY id DESC LIMIT ?",
                (conversation_id, history_limit),
            ).fetchall()
        return [dict(row) for row in reversed(rows)]

    def append(self, identity, cid, role, content):
        owner = self._owner(identity)
        message_role, message_content = self._message(role, content)
        conversation_id = self._conversation_id(cid, optional=True)
        with self._db() as db:
            if conversation_id:
                exists = db.execute(
                    "SELECT 1 FROM conversations WHERE id=? AND owner=?",
                    (conversation_id, owner),
                ).fetchone()
                if not exists:
                    raise PermissionError("conversa não encontrada")
            else:
                conversation_id = str(uuid.uuid4())
                title = message_content.replace("\\n", " ")[:72] or "Nova conversa"
                db.execute(
                    "INSERT INTO conversations(id,owner,title) VALUES(?,?,?)",
                    (conversation_id, owner, title),
                )
            db.execute(
                "INSERT INTO messages(conversation_id,role,content) VALUES(?,?,?)",
                (conversation_id, message_role, message_content),
            )
            db.execute(
                "UPDATE conversations SET updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (conversation_id,),
            )
        return conversation_id

    def delete(self, identity, cid):
        owner = self._owner(identity)
        conversation_id = self._conversation_id(cid)
        with self._db() as db:
            exists = db.execute(
                "SELECT 1 FROM conversations WHERE id=? AND owner=?",
                (conversation_id, owner),
            ).fetchone()
            if not exists:
                raise PermissionError("conversa não encontrada")
            db.execute("DELETE FROM messages WHERE conversation_id=?", (conversation_id,))
            db.execute(
                "DELETE FROM conversations WHERE id=? AND owner=?",
                (conversation_id, owner),
            )
        return True
