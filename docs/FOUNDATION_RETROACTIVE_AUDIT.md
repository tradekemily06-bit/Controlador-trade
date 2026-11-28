# Auditoria retroativa da fundação — 28 de novembro de 2026

## Objetivo e regra

Esta auditoria recupera trabalho anterior que não estava reconciliado no documento-mestre ou no mapa das seis áreas. Ela não declara conclusão por existência de arquivos. Cada item precisa ser separado entre: (1) artefato/contrato no código, (2) teste/CI, (3) integração no runtime/API, (4) validação externa e (5) aceitação da interface.

A auditoria é aditiva: não remove módulos, não cria uma sétima área, não altera o Lovable e não autoriza execução REAL.

## Descoberta crítica: o Project Master Specification estava desatualizado

O documento dizia que P53 era o último marco confirmado e que P54+ não deveriam ser preenchidos por inferência. A regra contra inventar marcos continua correta, mas a afirmação de que não havia marcos posteriores está desatualizada: o próprio repositório contém addenda, planos, implementações e testes posteriores.

### Marcos e documentos recuperados

| Faixa | Evidência recuperada | Estado honesto |
|---|---|---|
| P1–P22 | O master spec remete aos artefatos históricos do repositório, mas a auditoria ainda não recuperou individualmente todos os planos/testes dessa faixa. | Auditoria histórica pendente; não declarar perdidos nem concluídos em bloco. |
| P23–P53 | Planos, módulos e testes citados no master spec; inclui integridade de mercado, recuperação, segurança, intenção/lifecycle, alertas, contexto, risco, automação, reconciliação e primeira fronteira de aprendizagem. | Base histórica confirmada no repositório; requer verificação integrada por runtime, não apenas testes unitários. |
| P54–P60 | `ROADMAP_P54_P60_ADDENDUM.md`; validação de hipóteses, conhecimento confiável, uso controlado, memória, auditoria, laboratório e proposta de adaptação. | Planos e módulos/testes encontrados. A integração persistente com o runtime standalone e evidência de uso real ainda precisa ser comprovada. |
| P61–P70 | `core/p61_adaptation_evaluation.py` até `core/p70_adaptation_cycle_closure.py`; testes em `test_p61_p63_adaptation.py`, `test_p64_p66_adaptation_observation.py`, `test_p67_p70_adaptation_cycle.py`. | Contratos e testes encontrados; não confundir com adaptação automática ativa ou alteração autônoma da estratégia. |
| P71–P74 | Referenciados no fluxo P74 handoff e no teste de fechamento P71–P74. | Artefatos precisam de inventário individual e confirmação de integração. |
| P75–P79 | `ROADMAP_P75_P79_ADDENDUM.md`; validação de handoff, contexto de ciclo, auditoria, preparação de hipótese e admissão para validação. | Planos, módulos e testes encontrados; integração com Estudo e persistência operacional a comprovar. |
| P80–P85 | Especificação, execução, resultado, decisão, admissão de promoção e liberação de conhecimento confiável; teste `core/test_p80_p85_validation_promotion.py`. | Contratos e testes encontrados; a promoção não pode ser considerada produção sem dados representativos, trilha e gates operacionais. |
| P86–P89 | `ROADMAP_P86_P89_ADDENDUM.md`; auditoria, interpretação, escopo de uso e fechamento de governança. | Planos, módulos e testes encontrados; integração runtime/API não comprovada nesta auditoria. |
| P90–P95 | `ROADMAP_P90_P95_ADDENDUM.md`; solicitação, observação, avaliação, disposição, admissão e fechamento do uso controlado. | Planos, módulos e testes encontrados; não equivale a uso real ativo. |
| P96–P99 | `ROADMAP_P96_P99_ADDENDUM.md`; feedback operacional factual, avaliação, disposição e fechamento. | Planos, módulos e testes encontrados; origem factual e persistência precisam de aceitação ponta a ponta. |
| P100–P105 | `ROADMAP_P100_P105_ADDENDUM.md`; auditoria, arquivo, prontidão, contexto, hipótese e admissão. | Planos, módulos e testes encontrados; fluxo integrado com a interface não comprovado. |
| P106–P110 | `ROADMAP_P106_P110_ADDENDUM.md`; auditoria, especificação, registro, resultado e decisão de validação. | Planos, módulos e testes encontrados; não promover conhecimento sem a trilha completa e revisão. |
| P111–P119 | `ROADMAP_P111_P119_ADDENDUM.md`; auditoria pré-REAL, autorização explícita, multi-broker, barreira REAL, shadow/sandbox, admissão, observação e fechamento. | Contratos e planos existem; REAL permanece desabilitado no produto atual. Nenhum plano ou teste concede autorização operacional. |
| P120–P127 | Planos específicos: contrato de resultado, reconciliação externa, dados de mercado, ordem, sessão, sandbox/DEMO, segurança pré-REAL e integração IC Markets MT5 DEMO. | Fronteiras e adapter DEMO existem; a conexão do aplicativo standalone com conta real de provedor, por si só, ainda exige evidência atual de runtime. |
| P128–P149 | `PROJECT_COMPLETION_STATUS.md` declara artefatos posteriores; foram encontrados, entre outros, `core/p128_learning_handoff.py`, `integration/p138_result_learning_bridge.py` e `integration/p139_post_demo_learning.py`. | A declaração macro não basta. Fazer inventário arquivo a arquivo, testes, dependências, runtime e escopo antes de marcar a faixa concluída. |

**Importante:** os números P são identificadores históricos do projeto, não percentual de conclusão. Não inventar P150 ou qualquer marco posterior. O último número citado em documentação não substitui uma auditoria de integração.

## Contradições documentais que exigem correção

1. `PROJECT_MASTER_SPEC.md` e `docs/ADVANCED_INTELLIGENCE_TARGET.md` dizem que REAL permanece bloqueado.
2. A abertura de `docs/STANDALONE_COMPLETION_ROADMAP.md` afirma que o proprietário já autorizou ativação técnica de REAL.
3. `PROJECT_COMPLETION_STATUS.md` descreve contratos REAL existentes, mas também diz que REAL não está autorizado por padrão.
4. `P111–P119` define contratos de pré-REAL/liberação controlada, não uma autorização de operação em produção.
5. O requisito vigente desta fundação é manter SIMULAÇÃO e REAL desabilitado até nova decisão explícita e validação de segurança. Portanto, a frase de autorização genérica na abertura do roadmap é inconsistente e deve ser removida. Nenhuma credencial, contrato ou teste ativa REAL.

## Evidência histórica que não pode ser reaproveitada como prova atual

`PROJECT_COMPLETION_STATUS.md` registra um round-trip físico IC Markets MT5 DEMO em 01/10/2026. Isso deve ser preservado como evidência histórica do adapter/terminal naquele ambiente. Não prova que o novo aplicativo standalone hospedado esteja conectado agora, nem valida MT5 relay, credenciais, identidade, candles contínuos, timeframes anunciados ou notificações externas. A integração atual deve ter sua própria evidência com timestamp e ambiente identificados.

## Pendências antigas que permanecem abertas e devem entrar no plano de conclusão

### A. Recuperação de histórico e aprendizagem (P1–P149)
- Recuperar individualmente P1–P22 a partir de planos, commits, testes e histórico; não reconstruir conteúdo ausente.
- Inventariar P54–P149 arquivo por arquivo e mapear cada etapa para uma das seis áreas ou infraestrutura interna.
- Verificar se P54–P149 estão compostos no fluxo de Estudo/ runtime/API ou são contratos isolados.
- Verificar persistência, isolamento por tenant, backup/restore, proveniência e reversibilidade de todo o ciclo.
- Testar o handoff P128 e pontes P138/P139 com resultados DEMO reconciliados; nenhum resultado não verificado pode alimentar aprendizado.
- Impedir que conhecimento, hipóteses ou adaptação alterem estratégia, score, risco ou execução sem gates explícitos e avaliação out-of-sample.

### B. Dados, sinais e Estudo
- Conectar snapshots imutáveis originados do provider ao replay registrado; não aceitar candles arbitrários enviados pelo cliente como fonte verificada.
- Guardar source/provider ID, conta/tenant, símbolo canônico, timeframe, início/fim do candle, received_at, fechamento confirmado, checksum e status de lacunas/frescor.
- Adicionar spread, comissão, slippage, swaps e regras de preenchimento ao backtest; publicar métricas brutas e líquidas separadamente.
- Registrar todos os trials/variantes e séries de retorno temporalmente alinhadas; integrar PSR/DSR/CSCV/bootstrap/rolling windows e derivação defensável do número efetivo de trials.
- Preservar seleção e holdout cronológicos imutáveis; validar em dados realmente posteriores e não reutilizados.
- Não exibir probabilidade de lucro até haver outcomes representativos, calibração, drift e aprovação de política.

### C. Conexões e ciclos
- Provar MT5 relay com terminal DEMO real no novo fluxo standalone e provar cTrader com app Spotware/conta DEMO; validar OAuth, revogação, token vault/KMS, reconnect e stream.
- Confirmar símbolo, sessão, timezone, DST, feriados, fechamento antecipado, gaps e candle fechado por cada provider/timeframe anunciado.
- M1/M5/M10/M15 têm cobertura de testes, mas cada intervalo precisa de evidência externa de provider. D1/W1 permanecem fail-closed sem calendário de sessão confiável.
- TradingView é canal de alertas/webhooks, não feed contínuo de candles.
- Documentar limitações por broker e instrumento; não prometer compatibilidade universal.

### D. Notícias e calendário
- Configurar fontes oficiais e jornalísticas, validar feeds no runtime hospedado e acompanhar frescor/coverage por fonte.
- Buscar texto integral do artigo quando permitido, extrair afirmações, distinguir fato/alegação/rumor, identificar contradições e manter linhagem de fontes independentes.
- Ligar evento a ativos e contexto de mercado sem inferir direção por palavras-chave.
- Implementar adaptadores reais do calendário econômico oficial, inclusive fusos locais e eventos somente com data.
- Manter alertas de notícias como evidência não verificada; não são previsão nem instrução operacional.

### E. Notificações e operação contínua
- O inbox/outbox e Web Push são blocos de código, não prova de entrega.
- Ativar sink real, DNS/IP pinning e redirects seguros no sender, backend durável, KMS/VAPID, leases, retries, dead-letter e telemetria.
- Provar entrega e revogação em Android/iOS com navegador/app fechado.
- Rodar notícias, calendário, ciclos, notificações e backup sob supervisão hospedada; processo local não é serviço sempre ativo.

### F. Plataforma, dados e segurança
- Migrar de SQLite single-host para banco transacional compartilhado com migrations, tenant isolation, locks/leases distribuídos e limites transacionais.
- Configurar identidade confiável, sessões, TLS, CORS/CSRF, rate limits centralizados, rotação de segredos, KMS/envelope encryption e auditoria durável.
- Provar backups off-host, retenção, criptografia e restauração operacional real.
- Auditar rotas e permissões para garantir que Assistente do Ecossistema continue read-only e que não existam caminhos ocultos de ordem/movimentação financeira.

### G. Escopo funcional anterior e interface
- Implementar pipeline ponta a ponta de vídeo: ingestão, transcrição, extração visual, afirmações, conceitos, hipóteses e validação controlada. O escopo existe no master spec, mas não está provado como fluxo completo.
- Completar contexto persistente cross-asset/cross-market com validade temporal e evidência por relação.
- Completar síntese adversarial com evidência favorável, contrária, conflito, alternativa, lacunas e abstenção.
- Verificar Reserva Fiscal Brasil/Exterior com persistência, propriedade, reconciliação, exportação e recuperação.
- Verificar Assistente read-only, Study/replay, modo secreto e todos os módulos já mapeados.
- Fazer matriz de aceitação tela por tela dos seis painéis e controles no Lovable, sem mudar a aparência; validar loading/empty/stale/error/unauthorized e chamadas reais da API.

## Próxima sequência técnica obrigatória

1. Corrigir a documentação de autoridade REAL e reconciliar o master spec com os addenda P54–P127; manter P128–P149 como inventário pendente até revisão individual.
2. Fechar inventário P1–P149 sem omitir módulos e sem duplicar serviços.
3. Conectar snapshots de provider ao Estudo e criar backtest líquido de custos.
4. Integrar robustez/holdout e o ciclo de aprendizagem controlada com persistência e reversibilidade.
5. Validar fontes de notícias/calendário, conexões e notificações com ambiente externo real.
6. Fechar banco/identidade/KMS/backup/worker hospedado.
7. Completar aceitação das seis áreas no Lovable sem alteração visual.
8. Executar CI completo no código final e publicar relatório de conclusão com evidência por item.

## Estado desta auditoria

- Auditoria documental inicial: concluída para os artefatos acima.
- Auditoria individual P1–P22: pendente.
- Auditoria individual P54–P149: parcial; planos e famílias de módulos identificados, composição e runtime ainda precisam de verificação.
- Correção de conflito REAL: pendente até atualizar os documentos-fonte.
- Código/CI: a execução 46181167812 passou nos quatro jobs no head PR consultado; isso valida os testes/builds daquele head, não as pendências externas.
- PR #534 permanece draft, aberto e não mesclado.
- Sem alteração do Lovable, sem deploy, sem habilitar REAL, sem enviar ordens e sem movimentação de dinheiro.
