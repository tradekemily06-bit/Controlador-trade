import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from finance.fiscal_reserve import FiscalReserve
from finance.fiscal_schema import migrate_fiscal_schema

os.environ["CONTROLADOR_SINGLE_USER_IDENTITY"] = "test-owner"
from finance.fiscal_identity import configured_fiscal_owner_id
OWNER = configured_fiscal_owner_id()

def make_reserve(path):
    os.environ["CONTROLADOR_SINGLE_USER_IDENTITY"] = "test-owner"
    reserve = FiscalReserve(str(path))
    migrate_fiscal_schema(str(path))
    return reserve


def test_defaults_are_separate_and_configurable(tmp_path):
    reserve = make_reserve(tmp_path / "fiscal.sqlite3")
    assert reserve.settings(OWNER) == {"BR_DAY_TRADE": 20.0}
    reserve.update_rate(OWNER, "BR_DAY_TRADE", 18)
    assert reserve.settings(OWNER)["BR_DAY_TRADE"] == 18.0


def test_brazil_result_is_reserved_and_generic_foreign_result_is_blocked(tmp_path):
    reserve = make_reserve(tmp_path / "fiscal.sqlite3")
    brazil = reserve.record_realized_result(OWNER, {
        "category": "BR_DAY_TRADE",
        "realized_result_brl": 1000,
        "reference": "MT5-DEMO-TRADE-001",
        "occurred_on": "2026-10-29",
    })
    assert brazil["reserve_amount_brl"] == 200
    try:
        reserve.record_realized_result(OWNER, {
            "category": "FOREIGN_FINANCIAL_ASSET",
            "realized_result_brl": 2000,
            "reference": "BROKER-STATEMENT-001",
            "occurred_on": "2026-10-29",
        })
    except ValueError as exc:
        assert "classificação tributária" in str(exc)
    else:
        raise AssertionError("generic foreign results must remain unreserved")
    summary = reserve.summary(OWNER)
    assert summary["total_reserved_brl"] == 200
    assert summary["categories"]["BR_DAY_TRADE"]["reserve_amount_brl"] == 200
    assert summary["categories"]["FOREIGN_FINANCIAL_ASSET"]["reserve_amount_brl"] == 0
    assert len(summary["history"]) == 1


def test_losses_are_recorded_without_assuming_tax_loss_offsets(tmp_path):
    reserve = make_reserve(tmp_path / "fiscal.sqlite3")
    entry = reserve.record_realized_result(OWNER, {
        "category": "BR_DAY_TRADE",
        "realized_result_brl": -250,
        "reference": "TRADE-LOSS-001",
    })
    assert entry["realized_result_brl"] == -250
    assert entry["reserve_amount_brl"] == 0
    assert reserve.summary(OWNER)["categories"]["BR_DAY_TRADE"]["realized_result_brl"] == -250


def test_unknown_foreign_classification_is_rejected(tmp_path):
    reserve = make_reserve(tmp_path / "fiscal.sqlite3")
    try:
        reserve.record_realized_result(OWNER, {
            "category": "FOREIGN_CFD_UNCLASSIFIED",
            "realized_result_brl": 100,
            "reference": "FOREIGN-001",
        })
    except ValueError as exc:
        assert "categoria" in str(exc)
    else:
        raise AssertionError("unclassified foreign category must be rejected")


def test_reference_is_required_and_percent_is_bounded(tmp_path):
    reserve = make_reserve(tmp_path / "fiscal.sqlite3")
    try:
        reserve.record_realized_result(OWNER, {
            "category": "BR_DAY_TRADE",
            "realized_result_brl": 100,
        })
    except ValueError as exc:
        assert "reference" in str(exc)
    else:
        raise AssertionError("reference must be required")
    try:
        reserve.update_rate(OWNER, "BR_DAY_TRADE", 101)
    except ValueError as exc:
        assert "entre 0 e 100" in str(exc)
    else:
        raise AssertionError("rate above 100 must be rejected")



def test_duplicate_reference_is_rejected_without_double_reserving(tmp_path):
    reserve = make_reserve(tmp_path / "fiscal.sqlite3")
    payload = {
        "category": "BR_DAY_TRADE",
        "realized_result_brl": 1000,
        "reference": "CYCLE-UNIQUE-001",
    }
    reserve.record_realized_result(OWNER, payload)
    try:
        reserve.record_realized_result(OWNER, payload)
    except ValueError as exc:
        assert "já foi registrada" in str(exc)
    else:
        raise AssertionError("duplicate reference must not be counted twice")
    assert reserve.summary(OWNER)["total_reserved_brl"] == 200


def test_only_brazil_rate_can_be_updated_and_invalid_set_changes_nothing(tmp_path):
    reserve = make_reserve(tmp_path / "fiscal.sqlite3")
    reserve.update_rates(OWNER, {"BR_DAY_TRADE": 19})
    assert reserve.settings(OWNER) == {"BR_DAY_TRADE": 19.0}
    for attempt in (
        lambda: reserve.update_rate(OWNER, "FOREIGN_FINANCIAL_ASSET", 14),
        lambda: reserve.update_rates(OWNER, {"BR_DAY_TRADE": 18, "FOREIGN_FINANCIAL_ASSET": 14}),
    ):
        try:
            attempt()
        except ValueError:
            pass
        else:
            raise AssertionError("generic foreign rate changes must be rejected")
    try:
        reserve.update_rates(OWNER, {"BR_DAY_TRADE": 101})
    except ValueError:
        pass
    else:
        raise AssertionError("invalid Brazilian rate must be rejected")
    assert reserve.settings(OWNER) == {"BR_DAY_TRADE": 19.0}


def test_summary_exposes_day_week_month_and_year_totals(tmp_path):
    from datetime import date

    reserve = make_reserve(tmp_path / "fiscal.sqlite3")
    records = [
        ("2026-10-30", 100, "TODAY"),
        ("2026-10-28", 200, "THIS-WEEK"),
        ("2026-10-01", 300, "THIS-MONTH"),
        ("2026-09-30", 400, "THIS-YEAR"),
        ("2025-12-31", 500, "LAST-YEAR"),
    ]
    for occurred_on, amount, reference in records:
        reserve.record_realized_result(OWNER, {
            "category": "BR_DAY_TRADE",
            "realized_result_brl": amount,
            "reference": reference,
            "occurred_on": occurred_on,
        })

    summary = reserve.summary(OWNER, as_of=date(2026, 10, 30))
    assert set(summary["periods"]) == {"day", "week", "month", "year"}
    assert summary["periods"]["day"]["realized_result_brl"] == 100
    assert summary["periods"]["day"]["reserve_amount_brl"] == 20
    assert summary["periods"]["week"]["realized_result_brl"] == 300
    assert summary["periods"]["month"]["realized_result_brl"] == 600
    assert summary["periods"]["year"]["realized_result_brl"] == 1000


def test_date_must_be_exact_iso_calendar_date(tmp_path):
    reserve = make_reserve(tmp_path / "fiscal.sqlite3")
    for invalid in ("20261030", "30-10-2026", "2026-02-30"):
        try:
            reserve.record_realized_result(OWNER, {
                "category": "BR_DAY_TRADE",
                "realized_result_brl": 100,
                "reference": "INVALID-" + invalid,
                "occurred_on": invalid,
            })
        except ValueError as exc:
            assert "YYYY-MM-DD" in str(exc)
        else:
            raise AssertionError("non-ISO or invalid calendar date must be rejected")


def test_default_database_persists_between_operations(tmp_path):
    reserve = make_reserve(tmp_path / "memory-test.sqlite3")
    assert reserve.settings(OWNER)["BR_DAY_TRADE"] == 20.0
    entry = reserve.record_realized_result(OWNER, {
        "category": "BR_DAY_TRADE",
        "realized_result_brl": 100,
        "reference": "MEMORY-DB-001",
    })
    assert entry["reserve_amount_brl"] == 20
    assert reserve.summary(OWNER)["total_reserved_brl"] == 20



def test_history_pagination_returns_total_and_has_more(tmp_path):
    reserve = make_reserve(tmp_path / "fiscal.sqlite3")
    for number in range(5):
        reserve.record_realized_result(OWNER, {
            "category": "BR_DAY_TRADE",
            "realized_result_brl": 100 + number,
            "reference": f"PAGE-{number}",
            "occurred_on": "2026-10-30",
        })
    first = reserve.summary(OWNER, history_limit=2, history_offset=0)
    second = reserve.summary(OWNER, history_limit=2, history_offset=2)
    last = reserve.summary(OWNER, history_limit=2, history_offset=4)
    assert first["history_page"] == {"limit": 2, "offset": 0, "returned": 2, "total": 5, "has_more": True}
    assert second["history_page"]["has_more"] is True
    assert last["history_page"]["has_more"] is False
    assert len({row["reference"] for row in first["history"] + second["history"] + last["history"]}) == 5


def test_concurrent_duplicate_reference_is_never_double_recorded(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    reserve = make_reserve(tmp_path / "fiscal.sqlite3")
    payload = {
        "category": "BR_DAY_TRADE",
        "realized_result_brl": 1000,
        "reference": "CONCURRENT-UNIQUE-001",
    }

    def attempt():
        try:
            reserve.record_realized_result(OWNER, payload)
            return "created"
        except ValueError:
            return "duplicate"

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: attempt(), range(8)))

    assert results.count("created") == 1
    assert results.count("duplicate") == 7
    assert reserve.summary(OWNER)["total_reserved_brl"] == 200



def test_legacy_foreign_rows_are_preserved_but_excluded_from_all_reserve_totals(tmp_path):
    import sqlite3
    from datetime import date

    database = tmp_path / "legacy-fiscal.sqlite3"
    reserve = FiscalReserve(str(database))
    with sqlite3.connect(database) as db:
        db.execute(
            """INSERT INTO fiscal_reserve_entries
            (entry_id, category, entry_type, realized_result_brl, reserve_rate,
             reserve_amount_brl, reference, occurred_on, created_at, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            ("legacy-foreign-1", "FOREIGN_FINANCIAL_ASSET", "REALIZED_RESULT",
             1000.0, 15.0, 150.0, "LEGACY-FOREIGN-1", "2026-11-02",
             "2026-11-02T12:00:00+00:00", "legacy row"),
        )

    migrate_fiscal_schema(str(database))
    summary = reserve.summary(OWNER, as_of=date(2026, 11, 2))
    foreign = summary["categories"]["FOREIGN_FINANCIAL_ASSET"]
    assert summary["total_reserved_brl"] == 0.0
    assert summary["periods"]["day"]["realized_result_brl"] == 0.0
    assert summary["periods"]["day"]["reserve_amount_brl"] == 0.0
    assert foreign["entries"] == 1
    assert foreign["realized_result_brl"] == 0.0
    assert foreign["reserve_amount_brl"] == 0.0
    assert foreign["classification_status"] == "PENDING_CLASSIFICATION"
    assert foreign["rate_available"] is False
    # Keep the source record for audit; API presentation is sanitized separately.
    assert summary["history"][0]["reference"] == "LEGACY-FOREIGN-1"


def test_obsolete_foreign_rate_is_removed_without_deleting_legacy_history(tmp_path):
    import sqlite3

    database = tmp_path / "legacy-settings.sqlite3"
    with sqlite3.connect(database) as db:
        db.execute(
            "CREATE TABLE fiscal_reserve_settings (category TEXT PRIMARY KEY, rate REAL NOT NULL)"
        )
        db.execute(
            "INSERT INTO fiscal_reserve_settings(category, rate) VALUES (?, ?)",
            ("FOREIGN_FINANCIAL_ASSET", 15.0),
        )

    reserve = FiscalReserve(str(database))
    migrate_fiscal_schema(str(database))
    assert reserve.settings(OWNER) == {"BR_DAY_TRADE": 20.0}
    with sqlite3.connect(database) as db:
        remaining = db.execute(
            "SELECT category FROM fiscal_reserve_settings ORDER BY category"
        ).fetchall()
    assert remaining == [("BR_DAY_TRADE",)]


def test_money_rejects_boolean_values(tmp_path):
    reserve = make_reserve(tmp_path / "boolean-test.sqlite3")
    for value in (True, False):
        try:
            reserve.record_realized_result(OWNER, {"category": "BR_DAY_TRADE", "realized_result_brl": value, "reference": f"BOOL-{value}"})
        except ValueError:
            pass
        else:
            raise AssertionError("boolean must not be accepted as money")
        try:
            reserve.update_rate(OWNER, "BR_DAY_TRADE", value)
        except ValueError:
            pass
        else:
            raise AssertionError("boolean must not be accepted as a percentage")


def test_unverified_mt5_declarations_in_legacy_ledger_are_preserved_but_excluded_from_all_totals(tmp_path):
    from datetime import date
    import json

    reserve = make_reserve(tmp_path / "unverified-mt5.sqlite3")
    evidence = {
        "tax_classification_status": "USER_DECLARED_PENDING_REVIEW",
        "market_scope_source": "USER_DECLARATION_NOT_INDEPENDENTLY_VERIFIED",
        "independent_market_eligibility_verified": False,
        "tax_liability_confirmed": False,
        "reserve_semantics": "PLANNING_ESTIMATE_ONLY",
    }
    # Recreate a historical row written before the inclusion marker was
    # reserved by the service. New user notes must not be able to set this state.
    import sqlite3
    with sqlite3.connect(reserve.database_path) as db:
        db.execute(
            "INSERT INTO fiscal_reserve_entries "
            "(entry_id, owner_id, category, entry_type, realized_result_brl, "
            "reserve_rate, reserve_amount_brl, reference, occurred_on, created_at, notes) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "legacy-unverified-entry", OWNER, "BR_DAY_TRADE", "REALIZED_RESULT",
                250.0, 20.0, 50.0, "MT5-DEMO:UNVERIFIED-LEGACY-001",
                "2026-11-04", "2026-11-04T12:00:00+00:00",
                json.dumps(evidence, separators=(",", ":")),
            ),
        )

    summary = reserve.summary(OWNER, as_of=date(2026, 11, 4))
    assert summary["total_reserved_brl"] == 0.0
    assert summary["categories"]["BR_DAY_TRADE"]["entries"] == 0
    assert summary["categories"]["BR_DAY_TRADE"]["realized_result_brl"] == 0.0
    assert summary["categories"]["BR_DAY_TRADE"]["reserve_amount_brl"] == 0.0
    for period in ("day", "week", "month", "year"):
        assert summary["periods"][period]["entries"] == 0
        assert summary["periods"][period]["realized_result_brl"] == 0.0
        assert summary["periods"][period]["reserve_amount_brl"] == 0.0
    assert summary["history_page"]["total"] == 1
    assert summary["history"][0]["reference"] == "MT5-DEMO:UNVERIFIED-LEGACY-001"


def test_summary_discloses_planning_only_semantics_and_missing_monthly_offsets(tmp_path):
    reserve = make_reserve(tmp_path / "planning-semantics.sqlite3")
    reserve.record_realized_result(OWNER, {
        "category": "BR_DAY_TRADE",
        "realized_result_brl": 1000,
        "reference": "PLANNING-SEMANTICS-001",
        "occurred_on": "2026-11-04",
    })
    summary = reserve.summary(OWNER)
    semantics = summary["reserve_semantics"]
    assert semantics["kind"] == "PLANNING_ESTIMATE_ONLY"
    assert semantics["tax_liability_confirmed"] is False
    assert semantics["monthly_tax_assessment"] is False
    assert semantics["monthly_loss_offsets_calculated"] is False
    assert semantics["irrf_credits_calculated"] is False
    assert semantics["positive_entry_only"] is True
    assert "não é apuração mensal" in semantics["description"]


def test_every_public_reserve_operation_rejects_missing_or_invalid_owner(tmp_path):
    reserve = make_reserve(tmp_path / "owner-required.sqlite3")
    invalid_owners = ("", "   ", "x" * 161)
    for owner in invalid_owners:
        operations = (
            lambda: reserve.settings(owner),
            lambda: reserve.update_rate(owner, "BR_DAY_TRADE", 20),
            lambda: reserve.update_rates(owner, {"BR_DAY_TRADE": 20}),
            lambda: reserve.record_realized_result(owner, {
                "category": "BR_DAY_TRADE",
                "realized_result_brl": 100,
                "reference": "OWNER-REQUIRED-001",
            }),
            lambda: reserve.summary(owner),
        )
        for operation in operations:
            try:
                operation()
            except ValueError as exc:
                assert "identidade proprietária" in str(exc)
            else:
                raise AssertionError("fiscal reserve operation must reject invalid owner identity")


def test_reserve_rejects_coerced_numeric_values(tmp_path):
    reserve = make_reserve(tmp_path / "strict-reserve-money.sqlite3")
    for value in ("1000", True, [], {}, float("nan"), float("inf")):
        try:
            reserve.record_realized_result(OWNER, {
                "category": "BR_DAY_TRADE",
                "realized_result_brl": value,
                "reference": "STRICT-RESERVE-" + str(type(value).__name__) + str(value)[:5],
                "occurred_on": "2026-11-04",
            })
        except ValueError as exc:
            assert "realized_result_brl" in str(exc)
        else:
            raise AssertionError("reserve amount must reject coerced or non-finite values")
    for value in ("20", True, [], {}, float("nan"), float("inf")):
        try:
            reserve.update_rate(OWNER, "BR_DAY_TRADE", value)
        except ValueError as exc:
            assert "percentual" in str(exc)
        else:
            raise AssertionError("reserve rate must reject coerced or non-finite values")
    assert reserve.summary(OWNER)["total_reserved_brl"] == 0


def test_reserve_rejects_coerced_category_reference_date_and_notes(tmp_path):
    reserve = make_reserve(tmp_path / "strict-reserve-metadata.sqlite3")
    base = {
        "category": "BR_DAY_TRADE",
        "realized_result_brl": 100,
        "reference": "STRICT-METADATA-001",
        "occurred_on": "2026-11-04",
        "notes": "evidência",
    }
    for field, value in (
        ("category", ["BR_DAY_TRADE"]),
        ("reference", ["STRICT-METADATA-001"]),
        ("occurred_on", ["2026-11-04"]),
        ("notes", {"text": "evidência"}),
    ):
        try:
            reserve.record_realized_result(
                OWNER, {**base, field: value, "reference": "STRICT-" + field.upper()}
            )
        except ValueError:
            pass
        else:
            raise AssertionError(f"{field} must reject non-text values")
    assert reserve.summary(OWNER)["total_reserved_brl"] == 0



def test_reserve_settings_and_history_are_isolated_between_owner_ids(tmp_path):
    reserve = make_reserve(tmp_path / "fiscal-owner-isolation.sqlite3")
    owner_a = "single:owner-a"
    owner_b = "single:owner-b"

    reserve.update_rate(owner_a, "BR_DAY_TRADE", 17)
    reserve.record_realized_result(owner_a, {
        "category": "BR_DAY_TRADE",
        "realized_result_brl": 1000,
        "reference": "OWNER-A-TRADE-001",
        "occurred_on": "2026-11-04",
    })

    assert reserve.settings(owner_a) == {"BR_DAY_TRADE": 17.0}
    assert reserve.settings(owner_b) == {}
    assert reserve.summary(owner_b)["total_reserved_brl"] == 0
    assert reserve.summary(owner_b)["history"] == []

    reserve.update_rate(owner_b, "BR_DAY_TRADE", 23)
    assert reserve.settings(owner_a) == {"BR_DAY_TRADE": 17.0}
    assert reserve.settings(owner_b) == {"BR_DAY_TRADE": 23.0}
    assert reserve.summary(owner_a)["total_reserved_brl"] == 170
    assert reserve.summary(owner_b)["total_reserved_brl"] == 0


def test_user_notes_cannot_set_reserved_legacy_exclusion_marker(tmp_path):
    reserve = make_reserve(tmp_path / "reserved-marker.sqlite3")
    payload = {
        "category": "BR_DAY_TRADE",
        "realized_result_brl": 250.0,
        "reference": "USER-NOTE-MARKER-001",
        "occurred_on": "2026-11-04",
        "notes": "Anotação comum USER_DECLARED_PENDING_REVIEW",
    }
    import pytest
    with pytest.raises(ValueError, match="marcador interno reservado"):
        reserve.record_realized_result(OWNER, payload)
    assert reserve.summary(OWNER)["history_page"]["total"] == 0
    assert reserve.summary(OWNER)["total_reserved_brl"] == 0.0


def test_history_offset_is_bounded_before_sqlite_binding(tmp_path):
    reserve = make_reserve(tmp_path / "bounded-history.sqlite3")
    for invalid_offset in (-1, 1_000_000_001, 2**63):
        try:
            reserve.summary(OWNER, history_offset=invalid_offset)
        except ValueError as exc:
            assert "history_offset" in str(exc)
        else:
            raise AssertionError("out-of-range history offset must be rejected")
    valid = reserve.summary(OWNER, history_offset=1_000_000_000)
    assert valid["history_page"]["offset"] == 1_000_000_000
    assert valid["history"] == []


def test_fiscal_reserve_rejects_non_text_owner_identity(tmp_path):
    import pytest

    reserve = make_reserve(tmp_path / "strict-owner-identity.sqlite3")
    for invalid_owner in (None, 123, True, [], {}, object()):
        with pytest.raises(ValueError, match="identidade proprietária"):
            reserve.settings(invalid_owner)


def test_every_reserve_connection_enables_sqlite_foreign_keys(tmp_path):
    reserve = make_reserve(tmp_path / "foreign-keys.sqlite3")
    with reserve._connect() as db:
        assert db.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_reserve_rejects_future_realized_event_date(tmp_path):
    reserve = make_reserve(tmp_path / "future-reserve-event.sqlite3")
    tomorrow = (
        datetime.now(ZoneInfo("America/Sao_Paulo")).date() + timedelta(days=1)
    ).isoformat()
    with pytest.raises(ValueError, match="occurred_on não pode estar no futuro"):
        reserve.record_realized_result(OWNER, {
            "category": "BR_DAY_TRADE",
            "realized_result_brl": 100,
            "reference": "FUTURE-RESERVE-EVENT",
            "occurred_on": tomorrow,
        })
    assert reserve.summary(OWNER)["total_reserved_brl"] == 0
