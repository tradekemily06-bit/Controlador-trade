from __future__ import annotations
import json, os
from assistant.read_only_context import collect_read_only_context

class AssistantUnavailableError(RuntimeError): pass

SYSTEM_PROMPT=("Você é o Assistente do Ecossistema Controlador Trading. Responda em português claro. "
"Use apenas o contexto para fatos da conta; se faltar dado, diga indisponível. "
"Somente leitura: não envia ordens, não ativa REAL, não altera configurações nem movimenta dinheiro. "
"Reserva Fiscal é estimativa de planejamento, não apuração tributária. Não invente números.")
class EcosystemAssistant:
    def __init__(self,store,service,fiscal,client_factory=None,model=None):
        self.store,self.service,self.fiscal=store,service,fiscal
        self.client_factory=client_factory; self.model=model or os.getenv("OPENAI_MODEL","gpt-4o-mini")
    def _client(self):
        if self.client_factory: return self.client_factory()
        key=os.getenv("OPENAI_API_KEY","").strip()
        if not key: raise AssistantUnavailableError("Assistente não configurado: chave OpenAI ausente no servidor.")
        try: from openai import OpenAI
        except ImportError as exc: raise AssistantUnavailableError("Biblioteca OpenAI não instalada.") from exc
        return OpenAI(api_key=key)
    def conversations(self,identity): return self.store.list(identity)
    def history(self,identity,cid): return self.store.history(identity,cid)
    def ask(self,identity,message,cid=None):
        if not isinstance(message,str) or not message.strip() or len(message)>4000: raise ValueError("Mensagem deve ter de 1 a 4.000 caracteres.")
        context=collect_read_only_context(self.service,self.fiscal)
        cid=self.store.append(identity,cid,"user",message)
        history=self.store.history(identity,cid,12)
        messages=[{"role":"system","content":SYSTEM_PROMPT+"\nCONTEXTO JSON:\n"+json.dumps(context,ensure_ascii=False,default=str)[:24000]}]
        messages += [{"role":m["role"],"content":m["content"]} for m in history]
        try:
            response=self._client().chat.completions.create(model=self.model,messages=messages,temperature=0.2)
            answer=response.choices[0].message.content
            if not isinstance(answer,str) or not answer.strip(): raise ValueError("resposta vazia")
        except AssistantUnavailableError: raise
        except Exception as exc: raise AssistantUnavailableError("Não foi possível obter resposta agora; sua mensagem ficou no histórico.") from exc
        self.store.append(identity,cid,"assistant",answer)
        return {"conversation_id":cid,"answer":answer,"read_only":True,"execution_allowed":False}
