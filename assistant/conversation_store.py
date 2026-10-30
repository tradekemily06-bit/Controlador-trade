from __future__ import annotations
import hashlib, sqlite3, uuid
from pathlib import Path

class AssistantConversationStore:
    def __init__(self, path):
        self.path=Path(path); self.path.parent.mkdir(parents=True,exist_ok=True)
        with self._db() as db:
            db.execute("CREATE TABLE IF NOT EXISTS conversations(id TEXT PRIMARY KEY, owner TEXT NOT NULL, title TEXT NOT NULL, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")
            db.execute("CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY AUTOINCREMENT, conversation_id TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('user','assistant')), content TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")
            db.execute("CREATE INDEX IF NOT EXISTS conversations_owner ON conversations(owner,updated_at DESC)")
    def _db(self):
        db=sqlite3.connect(self.path,timeout=10); db.row_factory=sqlite3.Row; return db
    @staticmethod
    def _owner(identity):
        value=str(identity or "").strip().casefold()
        if not value: raise ValueError("identidade inválida")
        return hashlib.sha256(value.encode()).hexdigest()
    def list(self,identity):
        with self._db() as db:
            return [dict(x) for x in db.execute("SELECT id AS conversation_id,title,updated_at FROM conversations WHERE owner=? ORDER BY updated_at DESC LIMIT 30",(self._owner(identity),))]
    def history(self,identity,cid,limit=30):
        with self._db() as db:
            if not db.execute("SELECT 1 FROM conversations WHERE id=? AND owner=?",(cid,self._owner(identity))).fetchone(): raise PermissionError("conversa não encontrada")
            rows=db.execute("SELECT role,content,created_at FROM messages WHERE conversation_id=? ORDER BY id DESC LIMIT ?",(cid,max(1,min(int(limit),50)))).fetchall()
        return [dict(x) for x in reversed(rows)]
    def append(self,identity,cid,role,content):
        owner=self._owner(identity)
        if role not in ("user","assistant") or not content.strip(): raise ValueError("mensagem inválida")
        with self._db() as db:
            if cid:
                if not db.execute("SELECT 1 FROM conversations WHERE id=? AND owner=?",(cid,owner)).fetchone(): raise PermissionError("conversa não encontrada")
            else:
                cid=str(uuid.uuid4()); title=content.strip().replace("\n"," ")[:72] or "Nova conversa"
                db.execute("INSERT INTO conversations(id,owner,title) VALUES(?,?,?)",(cid,owner,title))
            db.execute("INSERT INTO messages(conversation_id,role,content) VALUES(?,?,?)",(cid,role,content.strip()))
            db.execute("UPDATE conversations SET updated_at=CURRENT_TIMESTAMP WHERE id=?",(cid,))
        return cid
