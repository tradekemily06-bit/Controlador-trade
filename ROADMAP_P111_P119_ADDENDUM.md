# Roadmap P111–P119 — fechamento e liberação REAL controlada

P111–P119 encerram a fase atual com foco em tornar o ecossistema apto a operar em REAL por meio de uma fronteira explícita e multi-corretora.

- P111: auditoria pré-REAL.
- P112: contrato de autorização REAL explícita.
- P113: arquitetura multi-corretora; o núcleo permanece independente de broker.
- P114: barreira de segurança REAL fail-closed.
- P115: shadow/sandbox validation sem envio REAL.
- P116: auditoria consolidada de liberação.
- P117: admissão REAL controlada.
- P118: observação factual do resultado externo, com UNKNOWN sem replay automático.
- P119: fechamento da fase e baseline P111–P119.

## Invariantes

1. O núcleo de decisão não conhece APIs de corretoras.
2. A integração ocorre por `BrokerAdapter`/`BrokerAdapterGateway`.
3. Mais de uma corretora pode ser registrada; nenhuma é requisito permanente.
4. REAL exige habilitação explícita e todas as barreiras de segurança.
5. Notícias, aprendizado e IA não recebem bypass para execução.
6. Falha, inconsistência ou indisponibilidade bloqueia em vez de executar por fallback silencioso.
7. P118 registra fatos externos; reconciliação e aprendizado permanecem nas fronteiras existentes.
8. A implementação não contém credenciais, chaves ou uma corretora concreta; a conexão concreta será adicionada como adaptador separado e configurável.
