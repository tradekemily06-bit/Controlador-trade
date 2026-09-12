# Methodology observation integration

The candle evaluator now consumes the broker-independent `CandleFeatures` layer through `MethodologyObservation`.

The integration centralizes observable candle geometry such as direction, body, range, wick measurements, close position, wick absence and wick symmetry.

The existing decision behavior is preserved: confirmation still compares the latest candle close with the previous candle close, and the existing SignalEngine remains responsible for COMPRA/VENDA/AGUARDAR.

No thresholds were invented for rejection, pressure, DDT, GAB, pullback, support/resistance, retirada de pavio or taxa dívida. Those rules will be added only when their definitions are explicit and testable.

No broker adapter is required and REAL execution remains disabled.
