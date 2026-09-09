# P21 — Runtime observability

Objetivo: adicionar uma camada somente leitura para observar a saúde do runtime e seus estados persistidos.

Inclui:
- contagem de ledger;
- estados PENDING/UNKNOWN;
- integração com RecoveryCoordinator;
- estados HEALTHY/ATTENTION/BLOCKED;
- fail-closed para estado inválido;
- nenhum caminho de execução ou replay.
