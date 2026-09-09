# P24 — Recovery Hardening

## Objetivo
Endurecer a avaliação de recuperação para impedir replay automático e tratar qualquer estado incerto como bloqueio operacional.

## Regras
- UNKNOWN exige reconciliação explícita;
- PENDING exige verificação;
- ACCEPTED sem ledger é inconsistente;
- estado persistido inválido => recuperação bloqueada;
- nenhuma ordem é executada ou repetida automaticamente.
