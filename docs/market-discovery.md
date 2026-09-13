# Open-ended market discovery

The market discovery layer derives neutral relationship signatures from the fields available in `GeneralMarketObservation`.

It is deliberately not a closed catalog of trading patterns. When new measurable observation fields are added, discovery can expose their scalar values and combinations without requiring every new relationship to be manually registered first.

## Safety boundary

Discovery is evidence, not a trading decision. It cannot authorize or emit `COMPRA`, `VENDA`, `AGUARDAR`, score, entry, confidence, risk, or execution instructions.

The intended flow is:

`market data -> broad observation -> relationship discovery -> neutral context -> validated decision layers -> risk gates -> execution gates`

A newly discovered relationship must be validated and explicitly admitted by the appropriate decision layer before it can influence an operational decision. Discovery alone never grants execution authority.
