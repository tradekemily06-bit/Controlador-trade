# P128 — Aprendizado e validação integrada do mercado

## Objetivo
Criar uma camada única para comparar conhecimento, hipóteses e descobertas com evidências observadas, preservando incerteza e impedindo que aprendizado isolado autorize operações.

## Requisitos
- aprender com resultados e evidências;
- submeter conhecimento/hipóteses às atividades e testes existentes do ecossistema antes de promoção;
- memorizar proveniência, evidências, resultado e contexto para aprendizado posterior;
- gerar perguntas de investigação (o quê, por quê, quando, em qual contexto e com quais evidências);
- reconhecer evidência favorável, contraditória, conflitante ou insuficiente;
- investigar operações potencialmente falsas e rompimentos potencialmente falsos sem codificá-los como regras fixas;
- permitir descobertas que não foram ensinadas pelo usuário;
- reduzir erro por validação, contraevidência e reavaliação, sem prometer infalibilidade;
- nunca conceder autorização de execução diretamente pela camada de aprendizado.

## Segurança
A camada de aprendizado não altera Risk Gate, não habilita REAL e não contorna o DecisionEngine. Conhecimento novo continua sujeito à validação e às barreiras operacionais já existentes.

## Próximo passo
Integrar esta avaliação ao fluxo existente de observação/contexto/hipótese/validação/memória, evitando duplicar os módulos P anteriores.
