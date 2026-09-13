# DEMO execution provider selection

The application remains PAPER by default.

To explicitly select the IC Markets MT5 DEMO adapter, set:

`CONTROLADOR_EXECUTION_PROVIDER=ic_markets_mt5_demo`

Optionally select a symbol with:

`CONTROLADOR_EXECUTION_SYMBOL=EURUSD`

The adapter does not store credentials. The MT5 terminal/runtime remains responsible for its own authenticated session. The adapter itself accepts only DEMO execution and the global REAL path remains blocked.

Any unsupported provider value fails during application construction instead of silently falling back to another executor.
