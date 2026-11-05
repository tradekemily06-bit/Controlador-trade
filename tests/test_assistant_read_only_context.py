from assistant.read_only_context import collect_read_only_context


class FakeService:
    def system_status(self):
        return {
            "mode": "SIMULACAO",
            "execution_allowed": False,
            "real": "DESABILITADO",
            "health": "OK",
            "components": {"mt5_demo": "NOT_CONNECTED"},
        }

    def risk_status(self):
        return {"allowed": False, "reason": "dados insuficientes"}

    def operational_observability(self):
        return {"execution": {"allowed": False, "mode": "DEMO"}}

    def statistics(self):
        return {"total_decisions": 3, "win_rate": 0.0}

    def memory_view(self, limit=50):
        assert limit == 5
        return [{"decision_id": "d-1", "signal": "AGUARDAR", "score": 30, "confirmed": False}]


class FakeFiscalReserve:
    def summary(self, owner_id):
        return {"name": "Reserva Fiscal", "total_reserved_brl": 0.0, "history": []}


def test_context_is_read_only_and_contains_existing_module_summaries():
    context = collect_read_only_context(FakeService(), FakeFiscalReserve(), "test-owner")

    assert context["system"]["mode"] == "SIMULACAO"
    assert context["system"]["execution_allowed"] is False
    assert context["system"]["real"] == "DESABILITADO"
    assert context["risk"]["allowed"] is False
    assert context["fiscal_reserve"]["total_reserved_brl"] == 0.0
    assert "decision_id" not in context["recent_decisions"][0]
    assert context["recent_decisions"][0]["signal"] == "AGUARDAR"
    assert context["assistant_safety"]["read_only"] is True
    assert context["assistant_safety"]["may_execute_orders"] is False
    assert context["assistant_safety"]["may_enable_real"] is False
    assert context["assistant_safety"]["may_move_money"] is False


def test_context_rejects_missing_dependencies():
    try:
        collect_read_only_context(None, FakeFiscalReserve(), "test-owner")
    except ValueError as exc:
        assert "obrigatórios" in str(exc)
    else:
        raise AssertionError("missing service must be rejected")



def test_context_sanitizes_all_legacy_foreign_tax_values():
    class FiscalWithLegacyForeignData:
        def summary(self, owner_id):
            return {
                "name": "Reserva Fiscal",
                "currency": "BRL",
                "total_reserved_brl": 10.0,
                "categories": {
                    "BR_DAY_TRADE": {"rate": 20.0, "realized_result_brl": 50.0, "reserve_amount_brl": 10.0},
                    "FOREIGN_FINANCIAL_ASSET": {
                        "rate": 15.0,
                        "entries": 2,
                        "realized_result_brl": 900.0,
                        "reserve_amount_brl": 135.0,
                        "notes": "informação legada",
                    },
                },
                "periods": {},
                "limitations": [],
                "history": [{"reference": "PRIVATE-FOREIGN-REF", "notes": "não enviar"}],
            }

    context = collect_read_only_context(FakeService(), FiscalWithLegacyForeignData(), "test-owner")
    foreign = context["fiscal_reserve"]["categories"]["FOREIGN_FINANCIAL_ASSET"]

    assert foreign == {
        "entries": 2,
        "realized_result_brl": 0.0,
        "reserve_amount_brl": 0.0,
        "classification_status": "PENDING_CLASSIFICATION",
        "rate_available": False,
    }
    assert "history" not in context["fiscal_reserve"]
    assert "PRIVATE-FOREIGN-REF" not in str(context)
    assert "informação legada" not in str(context)


def test_pending_queue_context_contract_is_read_only():
    class Queue:
        def summary(self, owner_id):
            assert owner_id == "test-owner"
            return {
                "total": 501,
                "realized_results": 500,
                "asset_amounts": 1,
                "currencies": ["USD", "EUR"],
                "as_of": "2026-11-03",
                "periods": {
                    "day": {"start": "2026-11-03", "end": "2026-11-03", "total": 2, "realized_results": 1, "asset_amounts": 1},
                    "week": {"start": "2026-11-02", "end": "2026-11-03", "total": 4, "realized_results": 3, "asset_amounts": 1},
                },
                "classification_status": "PENDING_CLASSIFICATION",
                "included_in_totals": False,
                "reserve_calculated": False,
            }
    context = collect_read_only_context(FakeService(), FakeFiscalReserve(), "test-owner", Queue())
    pending = context["fiscal_reserve"]["foreign_pending"]
    assert pending["total"] == 501
    assert pending["realized_results"] == 500
    assert pending["asset_amounts"] == 1
    assert pending["currencies"] == ["EUR", "USD"]
    assert pending["as_of"] == "2026-11-03"
    assert pending["periods"]["day"]["total"] == 2
    assert pending["periods"]["day"]["realized_results"] == 1
    assert pending["periods"]["week"]["asset_amounts"] == 1
    assert pending["included_in_totals"] is False
    assert pending["reserve_calculated"] is False

def test_assistant_receives_domestic_pending_counts_separately_without_values():
    class DomesticQueue:
        def summary(self, owner_id):
            assert owner_id == "test-owner"
            return {
                "total": 3,
                "as_of": "2026-11-04",
                "periods": {
                    "day": {"start": "2026-11-04", "end": "2026-11-04", "total": 1, "results": 1},
                    "week": {"start": "2026-11-02", "end": "2026-11-04", "total": 2, "results": 1},
                },
                "included_in_totals": False,
                "reserve_calculated": False,
            }

    context = collect_read_only_context(
        FakeService(), FakeFiscalReserve(), "test-owner",
        fiscal_domestic_pending_queue=DomesticQueue(),
    )
    domestic = context["fiscal_reserve"]["domestic_pending"]
    assert domestic["total"] == 3
    assert domestic["periods"]["day"]["results"] == 1
    assert domestic["included_in_totals"] is False
    assert domestic["reserve_calculated"] is False
    assert "realized_result_brl" not in str(domestic)


def test_assistant_foreign_pending_context_never_exposes_structured_user_declarations():
    class ForeignQueue:
        def summary(self, owner_id):
            assert owner_id == "test-owner"
            return {
                "total": 2,
                "realized_results": 1,
                "asset_amounts": 1,
                "currencies": ["USD"],
                "as_of": "2026-11-04",
                "periods": {
                    "day": {
                        "start": "2026-11-04",
                        "end": "2026-11-04",
                        "total": 2,
                        "realized_results": 1,
                        "asset_amounts": 1,
                    }
                },
                "items": [{
                    "reference": "PRIVATE-FOREIGN-REFERENCE",
                    "tax_residency_at_event": "BRAZIL",
                    "income_nature": "DIVIDEND",
                    "event_type": "DIVIDEND_RECEIPT",
                    "fx_conversion_method": "PTAX_SELL",
                    "notes": "PRIVATE-FOREIGN-NOTE",
                    "original_amount": 999999,
                    "original_currency": "USD",
                }],
                "included_in_totals": False,
                "reserve_calculated": False,
            }

    import json
    context = collect_read_only_context(
        FakeService(), FakeFiscalReserve(), "test-owner",
        fiscal_pending_queue=ForeignQueue(),
    )
    pending = context["fiscal_reserve"]["foreign_pending"]
    serialized = json.dumps(pending, ensure_ascii=False)
    assert pending["total"] == 2
    assert pending["currencies"] == ["USD"]
    assert pending["included_in_totals"] is False
    assert pending["reserve_calculated"] is False
    for private_value in (
        "PRIVATE-FOREIGN-REFERENCE", "PRIVATE-FOREIGN-NOTE",
        "tax_residency_at_event", "income_nature", "event_type",
        "fx_conversion_method", "original_amount", "999999",
    ):
        assert private_value not in serialized


def test_assistant_foreign_pending_context_fails_closed_when_owner_scoped_summary_fails():
    class BrokenForeignQueue:
        def summary(self, owner_id):
            assert owner_id == "test-owner"
            raise PermissionError("owner mismatch")

    context = collect_read_only_context(
        FakeService(), FakeFiscalReserve(), "test-owner",
        fiscal_pending_queue=BrokenForeignQueue(),
    )
    pending = context["fiscal_reserve"]["foreign_pending"]
    assert pending == {"available": False, "included_in_totals": False}



def test_assistant_receives_fiscal_reserve_totals_for_day_week_month_and_year():
    class FiscalWithPeriodTotals:
        def summary(self, owner_id):
            assert owner_id == "test-owner"
            return {
                "name": "Reserva Fiscal",
                "currency": "BRL",
                "as_of": "2026-11-05",
                "total_reserved_brl": 240.0,
                "categories": {
                    "BR_DAY_TRADE": {
                        "rate": 20.0,
                        "realized_result_brl": 1200.0,
                        "reserve_amount_brl": 240.0,
                    }
                },
                "periods": {
                    "day": {
                        "start": "2026-11-05",
                        "end": "2026-11-05",
                        "realized_result_brl": 200.0,
                        "reserve_amount_brl": 40.0,
                        "entries": 1,
                    },
                    "week": {
                        "start": "2026-11-02",
                        "end": "2026-11-05",
                        "realized_result_brl": 500.0,
                        "reserve_amount_brl": 100.0,
                        "entries": 3,
                    },
                    "month": {
                        "start": "2026-11-01",
                        "end": "2026-11-05",
                        "realized_result_brl": 900.0,
                        "reserve_amount_brl": 180.0,
                        "entries": 5,
                    },
                    "year": {
                        "start": "2026-01-01",
                        "end": "2026-11-05",
                        "realized_result_brl": 1200.0,
                        "reserve_amount_brl": 240.0,
                        "entries": 8,
                    },
                },
                "limitations": ["Estimativa de planejamento; não é imposto apurado."],
                "history": [{"reference": "PRIVATE-ENTRY-REF", "notes": "não enviar"}],
            }

    context = collect_read_only_context(
        FakeService(), FiscalWithPeriodTotals(), "test-owner"
    )

    fiscal = context["fiscal_reserve"]
    assert fiscal["as_of"] == "2026-11-05"
    assert fiscal["total_reserved_brl"] == 240.0
    assert fiscal["periods"]["day"]["reserve_amount_brl"] == 40.0
    assert fiscal["periods"]["week"]["realized_result_brl"] == 500.0
    assert fiscal["periods"]["month"]["reserve_amount_brl"] == 180.0
    assert fiscal["periods"]["year"]["realized_result_brl"] == 1200.0
    assert fiscal["limitations"] == ["Estimativa de planejamento; não é imposto apurado."]
    assert "history" not in fiscal
    assert "PRIVATE-ENTRY-REF" not in str(context)
    assert "não enviar" not in str(context)



def test_real_fiscal_reserve_period_totals_reach_assistant_context(tmp_path, monkeypatch):
    from datetime import date
    from finance.fiscal_identity import configured_fiscal_owner_id
    from finance.fiscal_reserve import FiscalReserve
    from finance.fiscal_schema import migrate_fiscal_schema

    monkeypatch.setenv("CONTROLADOR_SINGLE_USER_IDENTITY", "assistant-fiscal-integration-owner")
    owner_id = configured_fiscal_owner_id()
    database = tmp_path / "assistant-fiscal-integration.sqlite3"
    reserve = FiscalReserve(str(database))
    migrate_fiscal_schema(str(database))

    for occurred_on, amount, reference in (
        ("2026-11-05", 200.0, "ASSISTANT-PERIOD-DAY"),
        ("2026-11-04", 300.0, "ASSISTANT-PERIOD-WEEK"),
        ("2026-11-01", 400.0, "ASSISTANT-PERIOD-MONTH"),
        ("2026-01-01", 500.0, "ASSISTANT-PERIOD-YEAR"),
    ):
        reserve.record_realized_result(owner_id, {
            "category": "BR_DAY_TRADE",
            "realized_result_brl": amount,
            "reference": reference,
            "occurred_on": occurred_on,
        })

    class FixedDateFiscalReserve:
        def summary(self, requested_owner_id):
            assert requested_owner_id == owner_id
            return reserve.summary(requested_owner_id, as_of=date(2026, 11, 5))

    context = collect_read_only_context(
        FakeService(), FixedDateFiscalReserve(), owner_id
    )
    fiscal = context["fiscal_reserve"]

    assert fiscal["as_of"] == "2026-11-05"
    assert fiscal["periods"]["day"]["realized_result_brl"] == 200.0
    assert fiscal["periods"]["day"]["reserve_amount_brl"] == 40.0
    assert fiscal["periods"]["week"]["realized_result_brl"] == 500.0
    assert fiscal["periods"]["week"]["reserve_amount_brl"] == 100.0
    assert fiscal["periods"]["month"]["realized_result_brl"] == 900.0
    assert fiscal["periods"]["month"]["reserve_amount_brl"] == 180.0
    assert fiscal["periods"]["year"]["realized_result_brl"] == 1400.0
    assert fiscal["periods"]["year"]["reserve_amount_brl"] == 280.0
    assert fiscal["total_reserved_brl"] == 280.0
    assert fiscal["reserve_semantics"]["kind"] == "PLANNING_ESTIMATE_ONLY"
    assert fiscal["reserve_semantics"]["tax_liability_confirmed"] is False
    assert fiscal["reserve_semantics"]["monthly_tax_assessment"] is False
    assert fiscal["reserve_semantics"]["monthly_loss_offsets_calculated"] is False
    assert "history" not in fiscal
    assert "ASSISTANT-PERIOD-DAY" not in str(fiscal)
    assert context["assistant_safety"]["tax_estimates_are_not_tax_assessments"] is True


def test_assistant_fiscal_categories_forward_only_approved_aggregate_fields():
    class FiscalWithUnexpectedCategoryMetadata:
        def summary(self, owner_id):
            return {
                "name": "Reserva Fiscal",
                "categories": {
                    "BR_DAY_TRADE": {
                        "rate": 20.0,
                        "entries": 2,
                        "realized_result_brl": 100.0,
                        "reserve_amount_brl": 20.0,
                        "notes": "PRIVATE-BRAZIL-NOTE",
                        "reference": "PRIVATE-BRAZIL-REFERENCE",
                        "unexpected_future_field": "PRIVATE-FUTURE-FIELD",
                    },
                    "FOREIGN_FINANCIAL_ASSET": {
                        "entries": 3,
                        "rate": 15.0,
                        "realized_result_brl": 900.0,
                        "reserve_amount_brl": 135.0,
                        "notes": "PRIVATE-FOREIGN-NOTE",
                    },
                },
                "periods": {},
            }

    import json
    context = collect_read_only_context(
        FakeService(), FiscalWithUnexpectedCategoryMetadata(), "test-owner"
    )
    categories = context["fiscal_reserve"]["categories"]
    assert categories["BR_DAY_TRADE"] == {
        "entries": 2,
        "rate": 20.0,
        "realized_result_brl": 100.0,
        "reserve_amount_brl": 20.0,
    }
    assert categories["FOREIGN_FINANCIAL_ASSET"] == {
        "entries": 3,
        "realized_result_brl": 0.0,
        "reserve_amount_brl": 0.0,
        "classification_status": "PENDING_CLASSIFICATION",
        "rate_available": False,
    }
    serialized = json.dumps(categories, ensure_ascii=False)
    for private_value in (
        "PRIVATE-BRAZIL-NOTE",
        "PRIVATE-BRAZIL-REFERENCE",
        "PRIVATE-FUTURE-FIELD",
        "PRIVATE-FOREIGN-NOTE",
    ):
        assert private_value not in serialized
