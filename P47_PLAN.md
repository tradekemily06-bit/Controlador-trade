# P47 — Fechamento factual do ciclo automatizado

## Objetivo
Representar o encerramento de um ciclo automatizado a partir de um estado terminal P46, sem calcular resultado financeiro, sem reconciliar corretora e sem executar qualquer ação.

## Regras
- consumir somente ciclo P46 em `COMPLETED` ou `BLOCKED`;
- registrar o estado terminal e o instante de fechamento informado pelo chamador;
- aceitar apenas timestamp timezone-aware;
- não inventar WIN/LOSS, lucro, prejuízo ou resultado de mercado;
- não alterar ledger, risco, memória ou execução;
- resultado imutável e determinístico;
- entradas inválidas falham fechado.

## Critério de encerramento
Existe um contrato de fechamento que separa claramente o fato de um ciclo terminar do resultado financeiro de uma operação, deixando a integração com resultados reais para uma fronteira posterior e controlada.
