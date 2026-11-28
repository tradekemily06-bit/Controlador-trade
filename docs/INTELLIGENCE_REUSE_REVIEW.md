# Revisão de reaproveitamento — inteligência de mercado

Data da revisão: 28 de novembro de 2026.

## Critério

Reaproveitar somente mecanismos que aumentem a qualidade verificável da análise, evitem erros conhecidos ou acelerem uma capacidade que ainda falta. Não importar aplicações inteiras, interfaces, módulos duplicados ou dependências sem necessidade.

## OpenTerminalUI — licença MIT

Repositório: https://github.com/Marcikschmid/OpenTerminal
Licença: https://github.com/Marcikschmid/OpenTerminal/blob/main/LICENSE

### Adotado nesta etapa: validação estatística de estratégias

O Research Autopilot e o robustness scorecard oferecem uma abordagem útil: registrar o número de tentativas, avaliar retornos fora da amostra, corrigir a seleção entre múltiplas tentativas, usar bootstrap em blocos e observar estabilidade em janelas móveis. O projeto recebeu uma implementação independente e sem dependências NumPy em `analysis/strategy_robustness.py`.

A função exige retornos explicitamente marcados como fora da amostra, custos incluídos e benchmark alinhado. Calcula PSR, DSR, intervalo bootstrap e estabilidade. Resultado `ROBUST_REQUIRES_REVIEW` não promove estratégia, não é probabilidade de lucro e não concede autoridade de execução. A função ainda precisa ser integrada a um fluxo real de backtest/Estudo e validada no CI.

### Não duplicar: debate multiagente

O OpenTerminal implementa analistas fundamentalista, técnico e de sentimento, além de debate bull/bear e síntese. O Controlador-trade já possui leitura integrada com observações de múltiplos domínios, evidências favoráveis e contrárias, conflitos, perguntas não respondidas e reavaliação (`core/integrated_market_reading.py`, `core/senior_market_reasoning.py`, `core/senior_context_orchestrator.py`). Copiar outro orquestrador agora duplicaria a lógica. Uma camada LLM de debate só deve ser considerada depois de existir provider configurado, orçamento/limites e ferramentas read-only com proveniência.

## OpenTraderWorld — licença FSL-1.1-MIT

Repositório: https://github.com/G-OTW/OpenTraderWorld
Licença: https://github.com/G-OTW/OpenTraderWorld/blob/master/LICENSE

A licença atual restringe Competing Use — incluindo oferecer software comercial com funcionalidade igual ou substancialmente semelhante. Portanto, não copiar código desse repositório para o Ecossistema nesta fase. A licença concede uma licença MIT futura a partir do segundo aniversário da versão correspondente. Ideias de validação temporal e tratamento de lacunas podem ser implementadas independentemente, sem copiar código protegido.

## Próximas oportunidades, sem duplicação

1. Ligar a avaliação de robustez ao motor de backtest e à área Estudo, com divisão temporal intocada, baseline e ledger de tentativas.
2. Adicionar testes de causalidade/look-ahead e lacunas de candles ao backtest existente, aproveitando os princípios de teste documentados no OpenTraderWorld, mas com implementação própria.
3. Só depois avaliar um debate LLM multi-perspectiva, usando o mesmo conjunto de evidências verificadas e sem dar autoridade de execução ao modelo.

## Limites

Este reaproveitamento não significa que os dados de mercado, feeds, conectores, backtests ou notificações estejam em produção. Nenhum score estatístico substitui custos reais, qualidade dos dados, validação fora da amostra ou revisão humana.