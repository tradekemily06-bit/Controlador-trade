# MT5 validation gate

Software boundary: READY.

External runtime boundary: PENDING.

Required sequence: read-only health check, DEMO account confirmation, symbol and quote validation, order_check, one controlled DEMO order, external confirmation, close, reconciliation.

Any ambiguity keeps execution blocked.
