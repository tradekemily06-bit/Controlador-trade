# Controlador Trading — Project Master Specification

> Documento-mestre do escopo e das invariantes do projeto.
>
> **Status de referência:** P53 é o último marco do roadmap confirmado no repositório. P54+ não deve ser inventado: suas definições exatas devem ser recuperadas de uma especificação previamente acordada ou registradas quando forem explicitamente definidas.

## 1. Propósito

O Controlador Trading é um ecossistema de análise, decisão, segurança, execução controlada, auditoria, memória, pesquisa e aprendizado para mercados financeiros.

O objetivo é construir um sistema modular, verificável, determinístico onde apropriado, broker-agnostic e seguro por padrão. O sistema deve separar claramente:

- coleta e integridade de dados;
- contexto de mercado e notícias;
- análise e sinais;
- confluência e qualidade da oportunidade;
- risco e segurança operacional;
- decisão;
- intenção de execução;
- execução, quando futuramente habilitada de forma explícita;
- auditoria e resultados factuais;
- memória e aprendizado;
- laboratório, replay e simulação;
- inteligência/IA;
- dashboard e educação;
- componentes comerciais/afiliados.

O sistema **não deve prometer 100% de acerto**. Quando as evidências forem insuficientes ou conflitantes, a saída segura é **AGUARDAR** ou bloquear a ação.

---

## 2. Princípios arquiteturais permanentes

### 2.1 Broker-agnostic

O núcleo de decisão não deve depender de uma corretora específica. Adaptadores de dados e execução devem ficar nas bordas do sistema.

O sistema não deve ser centrado em Deriv. Corretoras/plataformas como Bullax, Adax Brock ou outras podem ser suportadas por adaptadores, sem contaminar o núcleo.

### 2.2 Separação de responsabilidades

Decisão, segurança, risco, aprendizado e execução devem permanecer em fronteiras separadas.

Uma camada não pode contornar uma camada de segurança simplesmente chamando diretamente uma implementação inferior.

### 2.3 Fail-closed

Entradas inválidas, estado inconsistente, dados não confiáveis, recuperação não reconciliada, configuração inválida ou condições de segurança não satisfeitas devem bloquear a progressão segura.

### 2.4 Execução REAL desabilitada por padrão

A arquitetura atual mantém a execução REAL bloqueada. O caminho de desenvolvimento deve permanecer seguro para DEMO/PAPER enquanto as fronteiras são construídas e validadas.

Nenhum módulo de aprendizado, notícia, IA ou sinal deve conseguir ativar execução REAL por conta própria.

### 2.5 Determinismo e auditabilidade

Onde não houver necessidade explícita de comportamento probabilístico, os componentes do núcleo devem produzir resultados determinísticos e verificáveis.

Eventos e decisões relevantes devem possuir identificadores, timestamps adequados e fatos preservados para auditoria.

### 2.6 Imutabilidade nas fronteiras

Contratos de entrada/saída que representam fatos, intenções, estados ou evidências devem ser imutáveis sempre que possível.

### 2.7 Sem inferências indevidas

O sistema deve distinguir claramente:

**fato observado → evidência verificada → hipótese → teste/validação → conhecimento confiável → eventual uso controlado**.

Uma hipótese não vira verdade porque apareceu muitas vezes, e uma única operação não prova causalidade ou generalização.

---

## 3. Arquitetura conceitual

### Camada de dados

- dados em tempo real;
- dados históricos;
- candles;
- trades;
- livro de ofertas/order book quando disponível;
- volume;
- spread;
- liquidez;
- normalização;
- cache e histórico;
- sincronização temporal;
- múltiplos ativos e timeframes;
- detecção de lacunas, anomalias e inconsistências.

### Camada de contexto

- notícias;
- eventos de mercado;
- janelas temporais;
- impacto explicitamente classificado;
- contexto por ativo;
- timezone consistente;
- agregação determinística.

Notícias/contexto podem informar análise, mas não devem gerar diretamente uma ordem.

### Camada de análise

Pode reunir, entre outros:

- price action;
- estrutura de mercado;
- tendência;
- volatilidade;
- momentum;
- suporte e resistência;
- topos e fundos;
- padrões;
- rompimentos e pullbacks;
- rejeições e pavios;
- pressão/força;
- volume;
- indicadores técnicos como fontes auxiliares.

O ecossistema deve permitir análise visual/price action sem exigir indicadores como condição universal.

### Camada de sinal e confluência

- COMPRA;
- VENDA;
- AGUARDAR;
- score/força;
- qualidade da oportunidade;
- níveis de sinal;
- confirmação de fechamento de candle quando aplicável;
- filtros de qualidade;
- combinação de evidências independentes.

Confluência não deve ser tratada como uma contagem artificial fixa. Evidências independentes e fortes têm mais peso que sinais redundantes.

### Camada de risco

- limite por operação;
- exposição atual e projetada;
- perda acumulada;
- perda projetada;
- limite diário de perda;
- orçamento de risco operacional;
- bloqueios de segurança;
- proteção contra valores inválidos/não finitos.

Não deve existir um limite artificial de quantidade diária de operações imposto pela estratégia. O sistema pode bloquear operações por risco, segurança ou qualidade.

### Camada de decisão

A decisão final deve combinar contexto, análise, qualidade, segurança e risco.

A decisão segura quando não há evidência suficiente é AGUARDAR.

### Camada de intenção

Uma decisão aprovada pode gerar uma intenção de execução validada e imutável, contendo os dados necessários para o handoff sem executar a operação.

### Camada de execução

A execução deve ficar atrás de uma interface/gateway explícita.

Não permitir chamadas diretas de módulos de estratégia, aprendizado, notícias ou IA para corretoras.

Estados de execução devem ser rastreáveis e não devem ser automaticamente repetidos quando houver estado terminal ou UNKNOWN sem reconciliação explícita.

### Camada de auditoria/resultados

Preservar fatos sobre:

- ciclo;
- decisão;
- intenção;
- admissão;
- lifecycle;
- fechamento;
- resultado observado;
- reconciliação.

O sistema não deve transformar ausência de informação em resultado inventado.

### Camada de memória e aprendizado

Somente fatos suficientemente verificados devem alimentar evidência confiável. Hipóteses devem permanecer explicitamente separadas de conhecimento validado.

### Laboratório

- replay;
- simulador de decisão;
- testes de hipóteses;
- comparação de condições;
- análise de padrões;
- análise de erros recorrentes;
- avaliação de qualidade;
- validação antes de qualquer promoção de conhecimento.

O laboratório não deve contaminar o núcleo operacional com conclusões ainda não validadas.

### IA/inteligência

A IA pode auxiliar em:

- descoberta;
- pesquisa;
- classificação;
- auditoria;
- diagnóstico;
- extração de conceitos;
- geração de hipóteses;
- análise de vídeos;
- identificação de padrões para investigação;
- adaptação controlada e supervisionada.

A IA não deve receber autoridade irrestrita para executar operações ou transformar hipóteses em regras automaticamente.

---

## 4. Fluxo de aprendizado

Fluxo conceitual oficial:

**resultado factual → evidência verificada → hipótese testável → teste/validação → conhecimento confiável → uso controlado**.

### Vídeos de mercados financeiros

O ecossistema deve ser capaz de receber/analisar vídeos sobre mercados financeiros.

Pipeline conceitual:

1. receber vídeo;
2. extrair/analisar transcrição;
3. analisar elementos visuais relevantes;
4. extrair conceitos e afirmações;
5. classificar conceito, contexto e origem;
6. registrar no conhecimento como material de referência/hipótese, não como verdade automática;
7. gerar hipóteses testáveis;
8. testar/validar em ambiente apropriado;
9. promover somente conhecimento que atenda aos critérios de confiança definidos;
10. disponibilizar conhecimento confiável para uso controlado pelo ecossistema.

Afirmações de um vídeo são alegações a serem verificadas, não fatos simplesmente porque foram apresentadas por alguém.

---

## 5. Notícias e contexto de mercado

O ecossistema deve ter acesso a notícias/contexto relevantes quando a integração correspondente estiver disponível.

Requisitos conceituais:

- timestamps e timezones consistentes;
- associação explícita ao ativo quando possível;
- janela temporal;
- impacto explicitamente representado;
- validação de origem/estrutura;
- agregação determinística;
- nenhuma inferência automática de sentimento como fato;
- nenhuma chamada direta para execução.

Notícia é contexto. Contexto pode alterar a avaliação de uma oportunidade, mas não substitui as fronteiras de segurança, risco e decisão.

---

## 6. Score, força e qualidade

O sistema deve suportar:

- score de sinal;
- força da oportunidade;
- qualidade da oportunidade;
- níveis de sinal;
- filtros de confirmação;
- identificação de condições fracas;
- AGUARDAR quando a qualidade não for suficiente.

O score não deve ser interpretado como probabilidade garantida de vitória.

Não usar um número arbitrário de indicadores redundantes para chamar algo de confluência. Priorizar evidências independentes, coerentes e relevantes para o contexto.

---

## 7. Memória e análise de desempenho

A memória do ecossistema deve poder registrar e analisar, conforme os dados confiáveis disponíveis:

- resultados por dia/semana/mês;
- condições de mercado;
- qualidade da oportunidade;
- padrões recorrentes;
- erros recorrentes;
- condições associadas a bons/maus resultados;
- histórico de decisões;
- evidências usadas;
- hipóteses e seu estado de validação.

A memória analítica deve respeitar a auditoria e a confiabilidade da origem. Não usar resultado não reconciliado como conhecimento confiável.

---

## 8. Replay, simulador e laboratório

O ecossistema deve permitir reproduzir decisões/condições sem depender da execução real.

Objetivos:

- reconstruir contexto;
- revisar entrada e decisão;
- testar hipóteses;
- comparar cenários;
- estudar erros;
- verificar regras antes de promoção.

Replay/simulação não devem alterar silenciosamente o estado operacional real.

---

## 9. Automação controlada

Automação deve possuir fronteiras explícitas:

- habilitação explícita;
- cadência/intervalo mínimo quando aplicável;
- timestamps timezone-aware;
- decisão de ciclo determinística;
- admissão de automação;
- handoff validado;
- lifecycle explícito;
- fechamento factual;
- resultado factual;
- reconciliação;
- aprendizagem somente após verificação.

Não usar timers, threads, retries automáticos, rede, corretora ou execução REAL dentro das fronteiras que foram definidas como read-only/decision-only.

---

## 10. Segurança operacional

Condições que devem poder bloquear progressão:

- kill switch ativo;
- dados de mercado não saudáveis;
- recuperação não reconciliada;
- configuração inválida;
- risco excedido;
- intenção inválida;
- modo REAL;
- estado operacional inconsistente;
- resultado/estado UNKNOWN sem reconciliação quando a fronteira exigir isso.

O bloqueio deve ser explícito, auditável e fail-closed.

---

## 11. Dashboard/UI — escopo conceitual

A interface deve poder expor, conforme os módulos forem implementados:

- operação;
- análise;
- sinais;
- score/força;
- qualidade/estabilidade;
- contexto/notícias;
- memória;
- laboratório;
- replay;
- automático;
- inteligência;
- padrões;
- erros recorrentes;
- resultados;
- auditoria;
- próximos gatilhos/condições relevantes.

A UI não deve contornar as regras do núcleo.

---

## 12. Educação e estudo

O ecossistema pode conter uma área de educação/estudo para:

- organizar conceitos;
- acompanhar aprendizado;
- revisar operações;
- estudar padrões;
- conectar conteúdo educacional às hipóteses testáveis;
- diferenciar conhecimento validado de material ainda não verificado.

---

## 13. Comercial e afiliados

O ecossistema pode conter um subsistema comercial/afiliados separado do núcleo de decisão.

Regras:

- não alterar sinais para fins comerciais;
- não alterar risco para fins comerciais;
- não permitir que comissão determine decisão de trading;
- manter separação entre operação técnica e monetização.

---

## 14. Marcos confirmados do roadmap

Os seguintes marcos foram confirmados no histórico do repositório e devem ser preservados como referência:

- **P23 — Market Data Integrity:** fronteira read-only de saúde de dados; HEALTHY, STALE, GAP, INVALID; valida ordenação, duplicidade, gaps, staleness, timestamps futuros, timezone e intervalo.
- **P24 — Recovery Hardening:** UNKNOWN exige reconciliação explícita; PENDING requer verificação; ACCEPTED sem ledger é inconsistente; estado persistido inválido bloqueia recovery; sem replay automático.
- **P25 — Unified Safety Gate:** READY_DEMO; REAL bloqueado; kill switch, dados não saudáveis, recovery não reconciliado e configuração inválida bloqueiam.
- **P26 — Execution Intent Contract:** contrato imutável de intenção; DEMO; sem acoplamento com broker/rede/execução.
- **P27 — Execution Intent Admission:** valida/admite intenção via ExecutionGateway; preserva request_id, símbolo, sinal, valor, duração e modo; fail-closed.
- **P28 — Execution Lifecycle Boundary:** PENDING → ACCEPTED/REJECTED/UNKNOWN; estados terminais não podem ser reutilizados; UNKNOWN exige reconciliação.
- **P29 — Execution Audit Boundary:** auditoria endurecida e integrada ao OperationalSafetyStore, preservando coexistência com kill switch e bloqueio de estado persistido inválido.
- **P30 — DEMO Execution Readiness Boundary:** combina safety gate e intenção DEMO válida; REAL bloqueado; sem execução.
- **P31 — Runtime Observability:** HealthState HEALTHY/ATTENTION/BLOCKED e RuntimeHealth com informações de ledger, pendências, UNKNOWN, recovery e mensagem; read-only/fail-closed.
- **P32:** fluxo DEMO unificado por P30 → P31 → ExecutionGateway, removendo caminho direto DemoFlow → PaperExecutor.
- **P33 — Operational Alerts Boundary.**
- **P34 — Safe Transport-Neutral Alert Delivery:** entrega segura sem rede/notificações externas.
- **P35 — Alert Deduplication/Suppression Safety.**
- **P36 — News and Market Context Boundary:** NewsEvent imutável, impacto explícito, timezone-aware, filtragem determinística e fail-closed.
- **P37 — Deterministic Market Context Aggregation:** snapshot imutável, contagens/distribuição e ordenação determinística.
- **P38:** conexão da qualidade do sinal ao contexto P37 sem alterar a qualidade original nem inferir sentimento.
- **P39 — Pre-Trade Risk Boundary:** limite por operação, exposição atual/projetada e bloqueio quando excedido; inválidos/não finitos falham fechado.
- **P40 — Operational Risk Budget:** perda acumulada/projetada, limite diário e operações máximas dentro do orçamento operacional; read-only.
- **P41 — Controlled Automation Boundary:** habilitação explícita, cadência mínima e timestamps timezone-aware; sem timers/threads/rede/broker/REAL.
- **P42:** ciclos de automação determinísticos baseados na decisão P41; DEMO-only; sem execução/rede/timers/REAL.
- **P43 — Automation Admission Boundary:** ciclo P42 + readiness DEMO P30 + orçamento P40; read-only.
- **P44 — Safe Automation-to-Intent Bridge:** handoff imutável entre admissão P43 e ExecutionIntent DEMO validada; sem execução.
- **P45 — Automation Audit Contract:** auditoria factual imutável do handoff P44; sem inferir resultado/lucro.
- **P46 — Controlled Automation Lifecycle:** CREATED → ADMITTED → DISPATCHED → COMPLETED, com estados de bloqueio a partir das etapas apropriadas; terminais não reutilizáveis.
- **P47 — Factual Automation Closure Boundary:** fechamento somente em COMPLETED/BLOCKED; sem inferência financeira.
- **P48 — Factual Automation Outcome Contract:** registra observação explicitamente fornecida, com WIN/LOSS/DRAW/UNKNOWN e resultado financeiro finito opcional; não infere.
- **P49 — Controlled Outcome Reconciliation:** MATCHED/MISMATCHED/UNVERIFIED; sem autocorreção.
- **P50 — Integrated Automation Result Snapshot:** compõe fechamento P47 + outcome P48 + reconciliação P49 em snapshot imutável.
- **P51 — Learning Ingestion Boundary:** classifica P50 em VERIFIED/UNVERIFIED/MISMATCHED; somente MATCHED é elegível para aprendizagem confiável.
- **P52 — Learning Evidence Contract:** somente P51 VERIFIED vira LearningEvidence factual; não afirma causalidade/generalização.
- **P53 — Learning Hypothesis Boundary:** P52 factual pode gerar LearningHypothesis testável; `validated=False`; hipótese não é conhecimento validado nem regra de trading.

### P1–P22

Os marcos anteriores existem no histórico do projeto, mas seus textos completos não estão reproduzidos aqui para evitar reconstrução incorreta. **Os artefatos existentes no repositório são a fonte de verdade para P1–P22.** Não inventar detalhes ausentes.

### P54 em diante

**Não preencher por inferência.** As definições exatas de P54, P55, P56 e posteriores devem ser adicionadas somente quando recuperadas de uma especificação anterior ou explicitamente definidas.

A ponte conceitual já estabelecida após P53 é:

**hipótese → teste/validação → conhecimento confiável → eventual uso controlado.**

Essa ponte não autoriza inventar o conteúdo exato de P54+.

---

## 15. Critérios de qualidade do projeto

Cada novo marco deve, quando aplicável:

1. ter objetivo explícito;
2. definir entradas e saídas;
3. definir invariantes de segurança;
4. possuir testes relevantes;
5. evitar acoplamento indevido;
6. falhar fechado diante de entradas inválidas;
7. preservar imutabilidade onde apropriado;
8. não introduzir execução REAL sem decisão explícita de arquitetura;
9. não transformar hipóteses em fatos;
10. não inventar resultados financeiros;
11. não introduzir rede/broker onde a fronteira é read-only;
12. manter auditabilidade;
13. ser compatível com a arquitetura broker-agnostic.

---

## 16. Regra de integridade do roadmap

Este documento existe para evitar perda de contexto, mas **não substitui evidência**.

Quando um marco antigo não estiver disponível literalmente:

- não reconstruir detalhes como se fossem certeza;
- marcar a informação como recuperada/conceitual;
- procurar primeiro no repositório, planos, commits, PRs e documentação existente;
- pedir confirmação somente quando a decisão for realmente necessária;
- nunca inventar um P54/P55/P56 apenas para preencher uma lacuna.

Quando um novo marco for acordado, atualizar este documento com:

- número e nome;
- objetivo;
- regras;
- entradas/saídas;
- dependências;
- restrições;
- critério de encerramento;
- status e referência ao código/PR quando aplicável.

---

## 17. Fonte de verdade

Prioridade das fontes para decisões futuras:

1. código e testes efetivamente presentes no repositório;
2. planos/documentação versionados no repositório;
3. PRs/commits e histórico do projeto;
4. decisões explícitas registradas durante o desenvolvimento;
5. este documento como consolidação do escopo;
6. memória/conversa apenas quando não houver fonte versionada melhor.

Se houver conflito, investigar e corrigir o documento em vez de mascarar a divergência.

---

## 18. Estado atual resumido

- Repositório: `tradekemily06-bit/Controlador-trade`
- Branch principal: `main`
- Proteção da `main`: ativa.
- P23–P53: confirmados como sequência atual do roadmap.
- P53: último marco confirmado.
- P54+: ainda não devem ser inventados.
- Execução REAL: bloqueada na arquitetura atual.
- Diretriz central: segurança, auditabilidade, separação de responsabilidades, aprendizado controlado e arquitetura broker-agnostic.

---

## 19. Nota de manutenção

Este arquivo é um **master spec vivo**. Ele deve ser atualizado quando uma decisão arquitetural importante ou um novo marco do roadmap for efetivamente acordado e implementado.

Não usar este arquivo para justificar uma implementação que contradiga código, testes ou regras de segurança existentes. Em caso de conflito, parar a promoção da mudança e reconciliar as fontes primeiro.
