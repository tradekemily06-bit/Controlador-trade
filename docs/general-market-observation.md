# General market observation layer

The ecosystem must not be a closed checklist containing only the user's named concepts.

`core/general_market_observation.py` provides a broker-independent observation layer that records broad, measurable candle and sequence context. Examples include direction sequences, same-direction streaks, candle range/body changes, volume changes, high/low/close progression, wick side, close position, wick symmetry, and no-wick candles.

These observations are deliberately neutral. A raw observation such as a candle with no wicks (a "vela careca") is recorded as context; it is not automatically converted into COMPRA or VENDA.

The architecture is intended to support a wider reasoning layer later:

`market data -> raw observations -> combinations/context -> known methodology rules when defined -> novel/uncategorized observations -> explanation -> decision/risk gates`

The observation layer must remain open-ended. New market characteristics can be added without requiring the user to pre-name them, and concepts whose exact methodology rules are not yet defined must not receive invented thresholds or trading classifications.

REAL execution remains outside this layer and remains blocked by the existing execution security boundary.
