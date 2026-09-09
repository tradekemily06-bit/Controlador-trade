# P48 — Contrato factual de resultado automatizado

## Objetivo
Representar um resultado externo já observado para um ciclo fechado, sem inferir WIN/LOSS, sem calcular lucro/prejuízo e sem executar qualquer ação.

## Regras
- consumir somente fechamento P47 válido;
- aceitar apenas resultado explicitamente informado pelo chamador;
- preservar ciclo, estado terminal e instante do resultado;
- resultado financeiro, quando informado, deve ser explícito e finito;
- não derivar resultado a partir de preço, duração ou estado do ciclo;
- não reconciliar corretora, alterar ledger, risco, memória ou execução;
- resultado imutável e determinístico;
- entradas inválidas falham fechado;
- REAL continua bloqueado.

## Critério de encerramento
Existe um contrato factual que separa o fato observado de qualquer interpretação posterior, permitindo que uma camada futura faça reconciliação controlada sem contaminar o fechamento do ciclo.
