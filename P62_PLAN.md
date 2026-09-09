# P62 — Aplicação controlada de adaptação

## Objetivo
Criar uma fronteira explícita para aplicar uma proposta somente quando sua avaliação P61 for APPROVED, mantendo a aplicação separada de execução de mercado.

## Regras
- consumir somente proposta P60 e avaliação P61 compatíveis;
- somente APPROVED pode avançar;
- aplicação deve ser identificável e explícita;
- não executar ordens, acessar corretora ou liberar REAL;
- não permitir aplicação duplicada ou reaplicação silenciosa;
- preservar proveniência;
- resultado imutável e fail-closed.

## Critério de encerramento
Uma adaptação aprovada pode ser representada como aplicada de forma controlada, sem confundir alteração de configuração/conhecimento com execução de mercado.
