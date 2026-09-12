# Market context reasoning

`core/market_context_reasoning.py` combines the broad observations produced by the general market observation layer into explainable context.

It can identify relationships such as:

- bullish/bearish/mixed directional context;
- rising, falling, or mixed high/low bounds;
- volume expansion or contraction;
- range expansion or contraction;
- direction streaks;
- simultaneous range/volume expansion or contraction;
- raw no-wick observations.

This is deliberately **not** a trading signal engine. It does not create COMPRA, VENDA, AGUARDAR, score, entry, confidence, or risk decisions. It also avoids invented numeric thresholds.

Architecture:

`market data -> raw observations -> context combinations -> methodology reasoning -> decision/risk gates`

The layer remains broker-independent and compatible with the existing REAL-disabled execution boundary.
