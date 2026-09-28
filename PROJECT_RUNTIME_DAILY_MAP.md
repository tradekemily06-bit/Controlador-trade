# Controlador Trading — Mapa Runtime Diário

## Estado desta composição

Esta documentação descreve a composição operacional comum. A prova concreta atual é DEMO; REAL continua desabilitado. DEMO e REAL devem atravessar as mesmas portas de execução, fechamento, observação, reconciliação, memória e aprendizado. A diferença de modo fica restrita à autorização, ao adapter/transport e à fronteira de segurança.

## 1. Caminho diário principal

```
dados/mercado
  ↓
contexto + análise
  ↓
DecisionSnapshot
  ↓
decisão + risco + admissão
  ↓
ExecutionGateway
  ↓
ExecutionLedger + ExecutionLifecycle
  ↓
OperationLineage
  ├─ decision_id
  ├─ cycle_id
  ├─ request_id
  └─ external_id
  ↓
OperationContextStore
  └─ snapshot original persistido por request_id
  ↓
adapter DEMO
  ↓
posição externa
  ↓
fechamento controlado
  ↓
external_container_id
  ↓
external_close_id
  ↓
posição ausente + deals de saída
  ↓
external_result_ids
  ↓
financial_result
  ↓
ExternalOutcomeObservation
  ↓
P49 — reconciliação factual
  ↓
P50 — snapshot de resultado
  ↓
P138/P139 — aprendizado pós-DEMO
  ↓
OperationLearningJournal
  ├─ identidade por cycle_id
  ├─ deduplicação persistente
  ├─ crescimento monotônico de deals
  └─ conflito de identidade bloqueado
  ↓
memória operacional + estatísticas + replay/laboratório
```

## 2. Identidades — não misturar dimensões

A conexão externa é composta por dimensões independentes:

- broker_id;
- platform_id;
- adapter_id;
- transport_id.

O registry usa nomes opacos. Não existe uma lista fixa de 2, 3, 4 ou 5 brokers.

O núcleo não conhece MT5, cTrader ou IC Markets.

## 3. Resultado externo

O resultado financeiro somente existe quando:

1. a execução DEMO foi aceita;
2. a identidade externa foi resolvida;
3. o fechamento foi confirmado;
4. a posição deixou de estar aberta;
5. existem deals de saída associados à posição;
6. os valores financeiros foram agregados;
7. a identidade dos deals foi persistida;
8. a observação externa foi reconciliada.

`order_send()` sozinho nunca significa WIN/LOSS.

## 4. Partial close, reversal e histórico atrasado

- Fechamento parcial: não gera resultado final enquanto a posição continuar aberta.
- `DEAL_ENTRY_OUT`, `DEAL_ENTRY_INOUT` e `DEAL_ENTRY_OUT_BY` entram na evidência de saída.
- Histórico atrasado pode ser reobservado.
- IDs de deals já persistidos nunca podem desaparecer.
- Novos IDs podem ser acrescentados.
- O aprendizado continua sendo um único registro por ciclo.
- Se os novos IDs forem incompatíveis, o aprendizado falha fechado.

## 5. Idempotência

Repetir o mesmo `request_id` depois de um fechamento aceito não envia outro fechamento.

A sequência passa a ser:

```
request_id já possui external_close_id
        ↓
reobserve
        ↓
se ainda incompleto → aguarda
se completo → reconcilia/aprende
```

O journal persistente usa SQLite no runtime diário e sobrevive a reinício.

## 6. Resultado fechado fora do botão

O ecossistema possui reconciliação pendente segura.

Ela:

- procura operações DEMO aceitas sem resultado externo final;
- consulta o adapter;
- pode descobrir a identidade externa de uma posição já fechada;
- nunca envia `order_send()`;
- somente transforma fato externo confirmado em memória/aprendizado.

Endpoint de manutenção:

`POST /api/outcome/reconcile`

O endpoint exige a mesma autorização DEMO da camada de controle remoto e informa explicitamente que nenhuma ordem foi enviada.

## 7. Estudo/replay versus operação

`POST /api/outcome` é mantido apenas como anotação de estudo/replay.

Ele retorna explicitamente:

- `study_only=true`;
- `execution_authorized=false`;
- `operational_result_verified=false`.

Resultado operacional confirmado vem exclusivamente da cadeia externa.

## 8. Recuperação

Após reinício:

- ledger permanece persistido;
- lifecycle permanece persistido;
- lineage permanece persistida;
- contexto da decisão permanece persistido;
- learning journal permanece persistido;
- recovery continua fail-closed;
- UNKNOWN não é executado novamente automaticamente;
- reconciliação observa fatos externos em vez de replayar ordens.

## 9. Brokers e plataformas futuras

### MT5 DEMO

Composição atual do adapter de resultado:

`ICMarketsMT5DemoOutcomeBridge → MT5ExternalOutcomeAdapter → ExternalOutcomePort`

MT5 fica na borda.

### REAL — mesma cadeia, outra fronteira

Quando REAL for autorizado, ele não recebe uma cadeia paralela. O `RealExecutionGateway` continua sendo a porta de admissão/execução REAL, enquanto o resultado financeiro deve entrar no mesmo `ExternalOutcomePort` e seguir P49 → P50 → P138/P139 → journal. A autorização REAL, o safety gate, o broker/adaptador e o ledger continuam específicos da fronteira REAL.

### cTrader

A infraestrutura de execução/autenticação cTrader já existe como território futuro, mas o adapter de resultado financeiro ainda deve ser implementado através da mesma `ExternalOutcomePort`.

Ele não deve criar uma cadeia paralela.

### Novos brokers

Um novo broker deve entrar por:

```
novo adapter
  ↓
AdapterConnectionIdentity
  ↓
BrokerRegistry / ExternalOutcomeRegistry
  ↓
ExecutionPort / ExternalOutcomePort
  ↓
mesmo gateway + mesma reconciliação + mesmo aprendizado
```

Não deve exigir alteração do núcleo de decisão.

## 10. REAL

REAL continua:

- DESABILITADO;
- não selecionável automaticamente;
- fora do caminho DEMO;
- sem autoridade derivada de aprendizado, IA, notícia, score ou resultado.

A existência de um adapter DEMO não concede autorização REAL.

## 11. O que está conectado nesta etapa

- execução DEMO → lineage;
- lineage → identidade externa;
- contexto da decisão → persistência;
- close → evidência financeira;
- reobserve → mesma cadeia;
- evidência → P49;
- P49/P50 → P138/P139;
- aprendizado → journal persistente;
- resultado confirmado → memória operacional/estatísticas;
- registry → composição broker/platform/adapter/transport;
- manutenção → reconciliação sem execução.

## 12. Próximo território, depois desta estabilização

Não é adicionar mais broker imediatamente.

A próxima etapa lógica é validar o ciclo diário completo em ambiente DEMO real:

```
analisar
→ decidir
→ validar risco
→ executar DEMO
→ permanecer acompanhado
→ fechar ou detectar fechamento externo
→ reconciliar
→ aprender
→ atualizar memória/estatísticas
→ iniciar próximo ciclo
```

Depois disso, a expansão para cTrader e outros brokers usa as mesmas portas.

Antes de qualquer REAL, o mesmo mapa deve ser revalidado com uma fronteira REAL separada e explicitamente autorizada.
