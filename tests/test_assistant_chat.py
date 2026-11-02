from types import SimpleNamespace
from assistant.conversation_store import AssistantConversationStore
from assistant.chat_service import EcosystemAssistant
from assistant.read_only_context import collect_read_only_context

class S:
 def system_status(self): return {"mode":"SIMULACAO","execution_allowed":False,"real":"DESABILITADO","health":"OK","components":{}}
 def risk_status(self): return {"allowed":False}
 def operational_observability(self): return {}
 def statistics(self): return {"total_decisions":0}
 def memory_view(self,limit=5): return []
class F:
 def summary(self):
  return {"total_reserved_brl":0,"as_of":"2026-10-30","periods":{"day":{},"week":{},"month":{},"year":{}},"history":[{"reference":"PRIVATE-TRADE-REFERENCE","notes":"PRIVATE-TRADE-NOTE"}]}
class C:
 calls=[]
 def __init__(self): self.chat=self; self.completions=self
 def create(self,**kw):
  self.calls.append(kw)
  return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="Resposta teste"))])

def test_chat_is_persistent_read_only_and_owner_scoped(tmp_path):
 store=AssistantConversationStore(tmp_path/"assistant.sqlite")
 a=EcosystemAssistant(store,S(),F(),client_factory=C)
 result=a.ask("one@example.com","Como está o sistema?")
 assert result["read_only"] and result["execution_allowed"] is False
 assert [m["role"] for m in store.history("one@example.com",result["conversation_id"])]==["user","assistant"]
 system_message=C.calls[-1]["messages"][0]["content"]
 assert "dia, semana, mês e ano" in system_message
 assert all(f'"{period}"' in system_message for period in ("day","week","month","year"))
 assert "não significa que foram lançados" in system_message
 assert "PRIVATE-TRADE-REFERENCE" not in system_message
 assert "PRIVATE-TRADE-NOTE" not in system_message
 try: store.history("two@example.com",result["conversation_id"])
 except PermissionError: pass
 else: assert False


def test_external_assistant_context_excludes_free_text_and_identifiers():
 class SensitiveService(S):
  def risk_status(self):
   return {"allowed":False,"reason":"PRIVATE-RISK-REASON","configured_limits":{"daily_loss_limit":100,"max_operations":3,"max_consecutive_losses":2}}
  def operational_observability(self):
   return {
    "execution":{"allowed":False,"mode":"DEMO","state":"BLOCKED","real":"DISABLED"},
    "reconciliation":{"state":"REQUIRED","pending_request_ids":["PRIVATE-REQUEST-ID"],"unknown_request_ids":[]},
    "recovery":{"state":"BLOCKED","can_resume":False,"message":"PRIVATE-RECOVERY-MESSAGE"},
    "kill_switch":{"state":"ACTIVE","enabled":True,"reason":"PRIVATE-KILL-REASON"},
    "runtime_health":{"state":"BLOCKED","ledger_entries":4,"pending_executions":1,"unknown_executions":0,"message":"PRIVATE-HEALTH-MESSAGE"},
    "market_data":{"health":"HEALTHY","safe_for_analysis":True,"symbol":"PRIVATE-SYMBOL","timeframe":"PRIVATE-TIMEFRAME","candle_count":20,"gap_count":0},
    "supervision":{"controller":{"token":"PRIVATE-SUPERVISOR-TOKEN"}},
   }
  def statistics(self):
   return {"total":2,"wins":1,"losses":1,"win_rate":50,"breakdowns":{"by_symbol":{"PRIVATE-SYMBOL":{"total":2}}}}
  def memory_view(self,limit=5):
   return [{"decision_id":"PRIVATE-DECISION-ID","created_at":"2026-10-30T12:00:00Z","symbol":"PRIVATE-SYMBOL","timeframe":"PRIVATE-TIMEFRAME","signal":"BUY","score":80,"confirmed":True,"reason":"PRIVATE-DECISION-REASON","outcome":"WIN"}]
 class SafeFiscal:
  def summary(self):
   return {"name":"Reserva Fiscal","currency":"BRL","as_of":"2026-10-30","categories":{},"total_reserved_brl":0,"periods":{},"limitations":[],"history":[{"notes":"PRIVATE-FISCAL-NOTE","reference":"PRIVATE-FISCAL-REFERENCE"}]}
 import json
 payload=json.dumps(collect_read_only_context(SensitiveService(),SafeFiscal()),ensure_ascii=False)
 for secret in ("PRIVATE-RISK-REASON","PRIVATE-REQUEST-ID","PRIVATE-RECOVERY-MESSAGE","PRIVATE-KILL-REASON","PRIVATE-HEALTH-MESSAGE","PRIVATE-SYMBOL","PRIVATE-TIMEFRAME","PRIVATE-SUPERVISOR-TOKEN","PRIVATE-DECISION-ID","PRIVATE-DECISION-REASON","PRIVATE-FISCAL-NOTE","PRIVATE-FISCAL-REFERENCE"):
  assert secret not in payload
 assert '"execution_allowed": false' in payload
 assert '"may_enable_real": false' in payload
 assert '"pending_count": 1' in payload
 assert '"wins": 1' in payload
