# Stage 7 — Release Governance & Controlled REAL Readiness

Stage 7 não habilita REAL. Ela prepara a revisão que poderá decidir, posteriormente e explicitamente, se existe base suficiente para uma habilitação controlada.

## Gates

- Stages 3–6 possuem evidência executável e rastreável;
- Stage 2 foi fechada somente quando sua matriz realmente estiver verde;
- side-door scan atualizado;
- threat model revisado;
- secrets/configuração de produção revisados;
- rollback e recuperação testados;
- reconciliação e UNKNOWN cobertos;
- incident response e kill switch documentados e testados;
- separação DEMO/REAL comprovada em código, configuração, API e UI;
- release checklist exige aprovação explícita para qualquer futura mudança de capacidade REAL.

## Proibição

Nenhum teste de Stage 7 deve enviar uma ordem REAL. Uma configuração ou flag não pode ser tratada como prova de autorização. A decisão de habilitar REAL será um gate posterior, separado e deliberado.
