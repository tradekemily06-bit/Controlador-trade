from types import SimpleNamespace
from assistant.conversation_store import AssistantConversationStore
from assistant.chat_service import EcosystemAssistant

class S:
 def system_status(self): return {"mode":"SIMULACAO","execution_allowed":False,"real":"DESABILITADO","health":"OK","components":{}}
 def risk_status(self): return {"allowed":False}
 def operational_observability(self): return {}
 def statistics(self): return {"total_decisions":0}
 def memory_view(self,limit=5): return []
class F:
 def summary(self): return {"total_reserved_brl":0}
class C:
 def __init__(self): self.chat=self; self.completions=self
 def create(self,**kw): return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="Resposta teste"))])

def test_chat_is_persistent_read_only_and_owner_scoped(tmp_path):
 store=AssistantConversationStore(tmp_path/"assistant.sqlite")
 a=EcosystemAssistant(store,S(),F(),client_factory=C)
 result=a.ask("one@example.com","Como está o sistema?")
 assert result["read_only"] and result["execution_allowed"] is False
 assert [m["role"] for m in store.history("one@example.com",result["conversation_id"])]==["user","assistant"]
 try: store.history("two@example.com",result["conversation_id"])
 except PermissionError: pass
 else: assert False
