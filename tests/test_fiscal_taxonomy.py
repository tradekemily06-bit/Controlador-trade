from finance.fiscal_taxonomy import (
    BRAZIL_CATEGORIES,
    FOREIGN_CATEGORIES,
    fiscal_classification_catalog,
)


def test_catalog_covers_distinct_brazilian_and_foreign_lanes_without_rates():
    catalog = fiscal_classification_catalog()

    assert catalog["tax_rates_included"] is False
    assert set(catalog["brazil"]) == set(BRAZIL_CATEGORIES)
    assert set(catalog["foreign"]) == set(FOREIGN_CATEGORIES)
    assert "BR_DAY_TRADE" in catalog["brazil"]
    assert "BR_COMMON_EXCHANGE" in catalog["brazil"]
    assert "BR_FII_FIAGRO" in catalog["brazil"]
    assert "BR_FIXED_INCOME" in catalog["brazil"]
    assert "BR_CRYPTO" in catalog["brazil"]
    assert "BR_FUTURES_OPTIONS" in catalog["brazil"]
    assert "FOREIGN_FINANCIAL_INVESTMENT" in catalog["foreign"]
    assert "FOREIGN_ENTITY_CONTROLLED" in catalog["foreign"]
    assert "FOREIGN_CRYPTO" in catalog["foreign"]


def test_only_existing_day_trade_flow_is_booking_enabled():
    catalog = fiscal_classification_catalog()

    assert catalog["brazil"]["BR_DAY_TRADE"]["booking_enabled"] is True
    assert all(
        item["booking_enabled"] is False
        for key, item in catalog["brazil"].items()
        if key != "BR_DAY_TRADE"
    )
    assert all(item["booking_enabled"] is False for item in catalog["foreign"].values())


def test_catalog_mutation_does_not_change_future_catalogs():
    first = fiscal_classification_catalog()
    first["brazil"]["BR_DAY_TRADE"]["requires"].append("tampering")
    first["foreign"]["FOREIGN_CRYPTO"]["limitations"].clear()

    second = fiscal_classification_catalog()
    assert "tampering" not in second["brazil"]["BR_DAY_TRADE"]["requires"]
    assert second["foreign"]["FOREIGN_CRYPTO"]["limitations"]


def test_every_non_automated_category_is_explicitly_pending_and_not_reserved():
    catalog = fiscal_classification_catalog()

    for group in (catalog["brazil"], catalog["foreign"]):
        for item in group.values():
            if item["calculation_status"] == "NOT_AUTOMATED":
                assert item["booking_enabled"] is False

    assert catalog["safety"] == {
        "unknown_category": "PENDING_CLASSIFICATION",
        "unimplemented_category": "PENDING_CLASSIFICATION",
        "pending_included_in_totals": False,
        "pending_reserve_calculated": False,
    }
