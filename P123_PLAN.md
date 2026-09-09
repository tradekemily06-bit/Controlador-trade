# P123 — Contrato de ordem da corretora

## Objetivo
Definir a tradução segura entre a decisão do núcleo e o formato de ordem que um adapter de corretora deve executar, sem colocar API, autenticação ou transporte no núcleo.

## Regras
- `COMPRA` vira `BUY`;
- `VENDA` vira `SELL`;
- `AGUARDAR` não pode virar ordem;
- quantidade/valor precisa ser finito e positivo;
- duração precisa ser positiva quando aplicável;
- `request_id` identifica a intenção e permanece estável durante retries/reconciliação;
- o adapter devolve aceitação/rejeição e, quando houver aceitação, o `external_id` da corretora;
- aceitação sem `external_id` permanece ambígua e é tratada pela barreira P120;
- nenhum adapter pode ativar REAL por conta própria.
