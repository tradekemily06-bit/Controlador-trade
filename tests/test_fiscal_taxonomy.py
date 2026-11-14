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


def test_only_supported_planning_flows_are_booking_enabled():
    catalog = fiscal_classification_catalog()

    assert catalog["brazil"]["BR_DAY_TRADE"]["booking_enabled"] is True
    assert all(
        item["booking_enabled"] is False
        for key, item in catalog["brazil"].items()
        if key != "BR_DAY_TRADE"
    )
    assert catalog["foreign"]["FOREIGN_FINANCIAL_INVESTMENT"]["booking_enabled"] is True
    assert catalog["foreign"]["FOREIGN_FINANCIAL_INVESTMENT"]["calculation_status"] == "PARTIAL_PLANNING_ONLY"
    assert catalog["foreign"]["FOREIGN_ENTITY_CONTROLLED"]["booking_enabled"] is False
    assert catalog["foreign"]["FOREIGN_CRYPTO"]["booking_enabled"] is False


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



def test_foreign_taxonomy_exposes_requirements_for_limited_planning_estimate():
    catalog = fiscal_classification_catalog()
    investment = catalog["foreign"]["FOREIGN_FINANCIAL_INVESTMENT"]
    crypto = catalog["foreign"]["FOREIGN_CRYPTO"]

    assert "instituicao_ou_autocustodia" in investment["requires"]
    assert "local_custodia" in investment["requires"]
    assert "tipo_de_contrato" in investment["requires"]
    assert "custo_de_aquisicao" in investment["recommended_evidence"]
    assert "imposto_pago_no_exterior" in investment["recommended_evidence"]
    assert "instituicao_ou_autocustodia" in crypto["requires"]
    assert investment["calculation_status"] == "PARTIAL_PLANNING_ONLY"
    assert investment["booking_enabled"] is True
    assert any("Forex, CFDs, índices, futuros" in item for item in investment["limitations"])
    assert crypto["calculation_status"] == "NOT_AUTOMATED"
    assert crypto["booking_enabled"] is False


def test_recommended_evidence_lists_are_copy_safe():
    first = fiscal_classification_catalog()
    first["foreign"]["FOREIGN_FINANCIAL_INVESTMENT"]["recommended_evidence"].append("tampering")
    second = fiscal_classification_catalog()
    assert "tampering" not in second["foreign"]["FOREIGN_FINANCIAL_INVESTMENT"]["recommended_evidence"]
