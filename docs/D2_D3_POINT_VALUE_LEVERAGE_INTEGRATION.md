# D2/D3 — PointValueEngine + alavancagem

## Regra de arquitetura

O valor monetário de ponto/tick/pip representa o efeito do movimento do preço sobre a quantidade negociada. **Alavancagem não multiplica esse valor novamente.**

- PointValueEngine: movimento → dinheiro.
- Alavancagem: capital → exposição/margem, conforme o modelo fornecido pelo broker/instrumento.
- Risco: perda potencial → orçamento de risco.
- Nenhuma dessas camadas decide COMPRA/VENDA nem autoriza REAL.

## Integridade das fontes

Quando uma operação fornece uma especificação dinâmica (`PointValueRequest`) e também um `value_per_price_unit` explícito, os valores devem coincidir. Divergência exige `REASSESS`; o sistema não escolhe silenciosamente uma fonte sobre a outra.

O modelo de margem também não é inferido por uma fórmula universal. `margin_required` deve vir do modelo de margem do broker/instrumento; ausência do modelo exige `REASSESS`.

## Estado

D2/D3 avançam sem criar teto funcional. O próximo trabalho é integrar a mesma avaliação à operação normal, sizing, risco, exposição, stop/P&L e replay, preservando proveniência, frescor e contexto histórico quando disponível.
