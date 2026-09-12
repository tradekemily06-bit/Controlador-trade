# Trading methodology feature layer

The methodology feature layer converts validated candles into broker-independent, deterministic observations.

It exposes candle direction, range, body size, upper/lower wick size, normalized ratios, close position, wick absence, and wick symmetry.

This layer intentionally does **not** decide COMPRA/VENDA, create a score, or invent thresholds for concepts whose exact rules still need to be defined from the user's methodology.

The resulting features are designed to support later rules such as rejection, pressure, DDT, GAB, pullback, support/resistance, retirada de pavio and taxa dívida without coupling the methodology to IC Markets MT5, cTrader, or another broker.
