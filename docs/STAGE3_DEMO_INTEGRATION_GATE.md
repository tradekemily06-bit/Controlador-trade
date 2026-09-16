# Stage 3 — DEMO Integration Gate

## Objetivo

Preparar a primeira integração concreta de produção em **DEMO/sandbox**, sem aumentar a capacidade de execução REAL. O primeiro alvo permanece IC Markets MT5 DEMO.

## Pré-condição

Este gate não autoriza integração REAL. A entrada em produção operacional depende da matriz final da Stage 2 estar verde e do CI consolidado ter concluído com sucesso.

## Gate A — composição

- O broker concreto entra somente através de `DemoBrokerExecutionPort`.
- O runtime fornece o estado de risco autoritativo e a barreira operacional.
- Nenhum módulo de aplicação recebe o adapter MT5 bruto.
- Nenhum caminho DEMO pode chamar o adapter bruto fora da fronteira autorizada.

## Gate B — identidade de mercado

Para cada requisição DEMO, a integração deve preservar de ponta a ponta:

`market-data identity -> symbol -> timeframe -> request_id -> broker_id -> adapter_id`

Uma mudança de símbolo, broker ou adapter durante o ciclo deve bloquear ou produzir estado incerto conforme o contrato, nunca uma execução silenciosamente aceita.

## Gate C — execução controlada

A integração deve provar, em DEMO/sandbox:

1. disponibilidade do terminal/adapter;
2. validação de contrato da ordem;
3. `order_check()` quando disponível;
4. envio controlado;
5. captura de `external_id`;
6. persistência no ledger;
7. reconciliação de resultado incerto;
8. bloqueio de duplicidade;
9. kill switch e incidente global bloqueando novas operações;
10. recuperação após restart sem duplicar envio.

## Gate D — falhas

Devem ser testados explicitamente:

- terminal indisponível;
- resposta inválida;
- timeout/exceção do adapter;
- aceite sem identificador externo;
- perda de conexão após envio;
- resultado UNKNOWN;
- restart durante estado RESERVED/UNKNOWN;
- símbolo divergente;
- adapter_id divergente;
- estado de risco alterado;
- decisão expirada.

A regra é **fail-closed para aquilo que não pode ser confirmado** e `UNKNOWN + reconciliação` quando o envio pode ter ocorrido.

## Gate E — observabilidade

O operador deve conseguir identificar sem acessar o adapter bruto:

- estado operacional;
- estado de risco;
- estado da execução;
- request_id;
- broker/adapter identity;
- external_id quando confirmado;
- necessidade de reconciliação;
- motivo de bloqueio.

Dados sensíveis e credenciais não entram em logs ou respostas públicas.

## Evidência exigida

A integração só passa quando existir uma suíte executável cobrindo os Gates A–E, CI verde no branch consolidado e evidência de restart/reconciliação. A existência da documentação, sozinha, não conta como aprovação.

## Separação Stage 2 / Stage 3

Se qualquer teste deste gate exigir relaxar uma barreira da Stage 2, o trabalho deve parar e voltar para Stage 2. Nenhuma adaptação temporária pode criar uma exceção permanente no caminho REAL.
