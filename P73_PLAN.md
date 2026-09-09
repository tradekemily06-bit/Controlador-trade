# P73 — admissão de eventual novo ciclo

Cria uma fronteira explícita entre o histórico arquivado e a preparação de um possível novo ciclo.

Somente arquivo P72 válido e elegibilidade `ELIGIBLE` podem produzir uma admissão `ADMITTED`. `NOT_ELIGIBLE` e `REVIEW_REQUIRED` bloqueiam a admissão. Nenhuma nova proposta é criada ou aplicada automaticamente.
