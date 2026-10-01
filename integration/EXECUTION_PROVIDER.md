The application does not bind itself to a broker by default.

The provider factory accepts `paper` as an isolated/test provider. The current Windows DEMO runtime explicitly selects IC Markets MT5 DEMO with:

`CONTROLADOR_EXECUTION_PROVIDER=ic_markets_mt5_demo`

Optionally select a symbol with:

`CONTROLADOR_EXECUTION_SYMBOL=EURUSD`

The adapter does not store credentials. The MT5 terminal/runtime remains responsible for its own authenticated session. The adapter itself accepts only DEMO execution and the global REAL path remains blocked.

Any unsupported provider value fails during application construction instead of silently falling back to another executor.
