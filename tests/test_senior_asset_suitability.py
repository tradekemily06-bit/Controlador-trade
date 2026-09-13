from core.senior_asset_suitability import (
    AssetSuitability,
    AssetSuitabilityObservation,
    assess_asset,
    prioritize_assets,
)


def complete(symbol="EURUSD"):
    return AssetSuitabilityObservation(
        symbol=symbol,
        asset_class="forex",
        tradeable=True,
        quote_available=True,
        session_open=True,
        weekend_capable=False,
        quote_fresh=True,
        spread_observed=0.8,
        liquidity_observed=True,
        data_quality_ok=True,
        domain_expertise_available=True,
    )


def test_complete_current_evidence_prioritizes_asset():
    result = assess_asset(complete())
    assert result.suitability is AssetSuitability.PRIORITY
    assert result.attention_priority is True


def test_missing_evidence_never_becomes_priority():
    result = assess_asset(
        AssetSuitabilityObservation(
            symbol="XAUUSD",
            asset_class="commodities",
            tradeable=True,
            quote_available=True,
            session_open=True,
            weekend_capable=False,
        )
    )
    assert result.suitability is not AssetSuitability.PRIORITY
    assert result.gaps


def test_closed_session_is_unavailable():
    result = assess_asset(complete())
    closed = assess_asset(
        AssetSuitabilityObservation(
            symbol=result.symbol,
            asset_class=result.asset_class,
            tradeable=True,
            quote_available=True,
            session_open=False,
            weekend_capable=False,
        )
    )
    assert closed.suitability is AssetSuitability.UNAVAILABLE


def test_bad_data_blocks_priority():
    observation = complete("BTCUSD")
    observation = AssetSuitabilityObservation(
        **{**observation.__dict__, "data_quality_ok": False}
    )
    result = assess_asset(observation)
    assert result.suitability is not AssetSuitability.PRIORITY
    assert "qualidade de dados inadequada" in result.gaps


def test_unvalidated_domain_expertise_cannot_produce_priority():
    observation = AssetSuitabilityObservation(
        **{**complete().__dict__, "domain_expertise_available": False}
    )
    result = assess_asset(observation)
    assert result.suitability is not AssetSuitability.PRIORITY
    assert any("expertise do domínio" in gap for gap in result.gaps)


def test_timestamp_does_not_claim_freshness_without_freshness_validation():
    observation = AssetSuitabilityObservation(
        **{**complete().__dict__, "quote_fresh": None, "quote_timestamped": True}
    )
    result = assess_asset(observation)
    assert result.suitability is not AssetSuitability.PRIORITY
    assert "frescura da cotação ainda não foi calculada" in result.gaps


def test_prioritization_does_not_prefer_crypto_or_weekend_by_class():
    forex = complete("EURUSD")
    crypto = AssetSuitabilityObservation(
        symbol="BTCUSD", asset_class="crypto", tradeable=True,
        quote_available=True, session_open=True, weekend_capable=True,
        quote_fresh=None, spread_observed=None, liquidity_observed=None,
        data_quality_ok=None, domain_expertise_available=True,
    )
    ranked = prioritize_assets((crypto, forex))
    assert ranked[0].symbol == "EURUSD"
