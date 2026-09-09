# P14 — Estado operacional durável

## Objetivo

Adicionar uma fronteira explícita de persistência ao fluxo operacional existente, permitindo restaurar a memória de operações após reinício sem alterar estratégia, decisão ou execução.

## Escopo

- carregar `OperationMemory` persistida na inicialização;
- salvar automaticamente após registrar uma operação;
- salvar automaticamente após liquidar uma operação `PENDENTE`;
- reutilizar `OperationMemoryStore` validado no P13;
- manter `P4OperationalRecorder` como autoridade de auditoria, memória e kill switch;
- rejeitar estado persistido inválido de forma segura;
- manter o caminho de execução e o bloqueio de REAL inalterados;
- cobrir recuperação e persistência com testes automatizados.

## Fora do escopo

- nenhuma nova estratégia;
- nenhuma alteração no `DecisionEngine`;
- nenhuma conexão com corretora real;
- nenhuma alteração no `ExecutionGateway`;
- nenhuma persistência de credenciais ou segredos;
- nenhuma alteração de regra de risco.

## Critérios de validação

1. Uma operação registrada permanece disponível após recriar o recorder a partir do mesmo arquivo.
2. Uma liquidação `WIN`/`LOSS` substitui o estado `PENDENTE` de forma persistente.
3. Metadados da operação permanecem íntegros.
4. Arquivo inválido falha fechado com erro explícito.
5. Testes existentes permanecem verdes.
6. Execução continua separada da persistência.
