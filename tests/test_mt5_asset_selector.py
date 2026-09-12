from types import SimpleNamespace

import pytest

from execution.mt5_asset_selector import rank_mt5_assets
from execution.mt5_instrument_universe import MT5InstrumentStatus


def status(symbol, *, tradeable=True, quote_available=True, weekend_capable=False, asset_class="other"):
    return MT5InstrumentStatus(
        symbol=symbol,
        asset_class=asset_class,
        visible=True,
        tradeable=tradeable,
        quote_available=quote_available,
        weekend_capable=weekend_capable,
        state="OPEN" if tradeable else "CLOSED",
        reason="test",
    )


def test_rank_prefers_weekend_crypto_then_other_eligible_assets():
    ranked = rank_mt5_assets(
        [
            status("EURUSD"),
            status("SOLUSD", weekend_capable=True, asset_class="crypto"),
            status("ADAUSD", weekend_capable=True, asset_class="crypto"),
            status("CLOSED", tradeable=False),
            status("NOQUOTE", quote_available=False),
        ]
    )

    assert [item.symbol for item in ranked] == ["ADAUSD", "SOLUSD", "EURUSD"]
    assert [item.rank for item in ranked] == [1, 2, 3]


def test_rank_limit_is_applied_after_filtering():
    ranked = rank_mt5_assets(
        [
            status("BTCUSD", weekend_capable=True, asset_class="crypto"),
            status("ETHUSD", weekend_capable=True, asset_class="crypto"),
            status("LTCUSD", weekend_capable=True, asset_class="crypto"),
        ],
        limit=2,
    )

    assert [item.symbol for item in ranked] == ["BTCUSD", "ETHUSD"]


def test_rank_rejects_negative_limit():
    with pytest.raises(ValueError, match="non-negative"):
        rank_mt5_assets([], limit=-1)
