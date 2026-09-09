# P44 — Ponte segura entre admissão automatizada e intenção DEMO

## Objetivo
Criar uma fronteira explícita que transforme uma admissão P43 aprovada e uma `ExecutionIntent` DEMO já validada em um plano imutável de próximo passo, sem executar a operação.

## Regras
- consumir somente uma `AutomationAdmissionResult` aprovada do P43;
- consumir somente uma `ExecutionIntent` já validada;
- aceitar exclusivamente intenção em modo DEMO;
- produzir um artefato imutável que preserve a intenção e identifique o ciclo automatizado;
- rejeitar admissão bloqueada, intenção ausente ou inválida e modo REAL;
- não chamar `ExecutionGateway`, executor, corretora ou rede;
- não criar timers, threads, retries ou mutação de estado;
- falhar fechado em entradas inválidas;
- manter a decisão separada da execução: o plano apenas autoriza o próximo passo estrutural.

## Critério de encerramento
Existe uma fronteira testada que conecta P43 a uma intenção DEMO válida sem executar nada, preservando o isolamento da execução e deixando o artefato pronto para uma etapa posterior de despacho controlado.
