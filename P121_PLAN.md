# P121 — Reconciliação externa de ordem REAL

## Objetivo
Criar uma fronteira broker-agnostic para consultar o estado externo de uma ordem por `external_id`, sem reenviar a ordem.

## Estados externos
- EXECUTED
- NOT_EXECUTED
- PENDING
- UNKNOWN

Somente EXECUTED e NOT_EXECUTED encerram a reconciliação. PENDING/UNKNOWN permanecem não resolvidos.

## Invariantes
- consulta é somente leitura;
- nenhuma consulta dispara nova ordem;
- `external_id` precisa coincidir;
- adapter específico permanece fora do núcleo;
- REAL não é ativado por esta etapa.
