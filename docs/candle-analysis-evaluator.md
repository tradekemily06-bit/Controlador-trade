# Candle analysis evaluator

The candle evaluator is a deterministic, read-only analysis layer between validated MT5 market data and the existing signal model.

It uses only completed candles from the market-data boundary and evaluates direction, candle-body strength, close location, and close-to-close confirmation.

It does not place, modify, or close orders. It does not enable REAL execution. Its score is an analysis input and is not a guarantee of outcome.

The methodology remains intentionally conservative and can be expanded later with the project's defined trading concepts (structure, rejection, pressure, DDT, GAB, pullback, support/resistance and related confirmations) without coupling those concepts to the broker adapter.
