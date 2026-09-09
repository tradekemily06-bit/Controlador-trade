# P42 — Orquestração determinística de ciclos automatizados

## Objetivo
Criar a camada que transforma uma autorização P41 em um pedido explícito de ciclo, sem executar análise, ordens ou efeitos externos.

## Regras
- consumir somente autorização válida da fronteira P41;
- cada ciclo possui identificador, instante e modo DEMO;
- não iniciar ciclo quando P41 bloquear;
- resultado imutável e determinístico;
- nenhum timer, thread, rede, corretora ou execução REAL;
- não alterar risco, memória, kill switch ou estado operacional.

## Critério de encerramento
Uma fronteira testada converte autorização de automação em um pedido de ciclo explícito e seguro, mantendo análise e execução fora desta camada.