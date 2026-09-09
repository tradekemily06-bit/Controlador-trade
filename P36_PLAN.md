# P36 — Contexto de notícias e mercado

## Objetivo
Estabelecer uma fronteira broker-agnóstica e somente de leitura para contexto de notícias/mercado, permitindo que fontes externas sejam incorporadas futuramente sem acoplar o núcleo de decisão a provedores, APIs ou canais de distribuição.

## Regras
- notícias entram por contrato explícito e normalizado;
- cada evento possui horário, título, fonte, símbolos relacionados e impacto declarado pela fonte/ingestor;
- não inferir sentimento ou impacto automaticamente nesta etapa;
- eventos precisam ter timestamp timezone-aware e campos textuais não vazios;
- contexto retornado é imutável e deterministicamente ordenado;
- filtragem por símbolo e janela temporal ocorre somente sobre eventos já validados;
- nenhuma chamada de rede, corretora, execução, alerta ou alteração de estado;
- falhar fechado para entradas inválidas;
- preservar separação entre contexto de mercado, estratégia, risco e execução.

## Critério de encerramento
Existe um contrato de contexto de notícias testado que aceita somente eventos normalizados e válidos, permite consulta determinística por símbolo/janela e permanece independente de qualquer provedor externo.

## Próxima etapa
Integrações concretas de provedores podem consumir este contrato sem alterar o núcleo. O contexto não deve, por si só, autorizar ou bloquear uma operação nesta fase.
