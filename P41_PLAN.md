# P41 — Fronteira de automação controlada

## Objetivo
Estabelecer uma fronteira determinística para decidir quando um ciclo automatizado pode ser solicitado, sem transformar a automação em execução de ordens.

## Regras
- automação deve ser explicitamente habilitada;
- cada avaliação recebe um identificador de ciclo e um instante timezone-aware;
- deve existir um intervalo mínimo entre ciclos;
- um ciclo não pode ser autorizado antes do intervalo mínimo;
- valores inválidos ou não finitos bloqueiam (fail-closed);
- a fronteira é somente leitura e não dispara threads, timers, rede, corretoras ou ordens;
- não altera estado de risco, kill switch, memória ou execução;
- REAL permanece bloqueado;
- resultado deve ser imutável e determinístico para os mesmos dados de entrada.

## Critério de encerramento
Existe uma fronteira testada que avalia habilitação e cadência de automação e retorna uma autorização factual para iniciar um ciclo, sem executar nenhuma ação externa ou operacional.

## Próxima etapa
Uma camada posterior poderá orquestrar ciclos usando esta autorização, mantendo a execução separada e sujeita às fronteiras de segurança já existentes.