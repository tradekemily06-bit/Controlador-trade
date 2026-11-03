from finance.fiscal_pending_queue import FiscalPendingQueue


def sample(reference="FOREIGN-STATEMENT-001"):
    return {
        "reference": reference,
        "original_amount": 125.50,
        "original_currency": "USD",
        "instrument": "ETF",
        "jurisdiction": "US",
        "occurred_on": "2026-10-30",
        "fx_rate": 5.42,
        "fx_date": "2026-10-30",
        "fx_source": "Banco Central - cotação informada",
    }


def test_foreign_item_is_persisted_as_pending_without_tax_calculation(tmp_path):
    queue = FiscalPendingQueue(str(tmp_path / "fiscal.sqlite3"))
    item = queue.add(sample())
    assert item["status"] == "PENDING_CLASSIFICATION"
    assert item["original_amount"] == 125.5
    assert item["original_currency"] == "USD"
    result = queue.list_pending()
    assert result["total"] == 1
    assert result["items"][0]["reference"] == "FOREIGN-STATEMENT-001"
    assert "não integram os totais" in result["note"]


def test_duplicate_reference_is_rejected(tmp_path):
    queue = FiscalPendingQueue(str(tmp_path / "fiscal.sqlite3"))
    queue.add(sample())
    try:
        queue.add(sample())
    except Exception as exc:
        assert "UNIQUE" in str(exc).upper()
    else:
        raise AssertionError("duplicate reference must be rejected")


def test_fx_evidence_must_be_complete(tmp_path):
    queue = FiscalPendingQueue(str(tmp_path / "fiscal.sqlite3"))
    payload = sample()
    payload["fx_source"] = ""
    try:
        queue.add(payload)
    except ValueError as exc:
        assert "fx_date e fx_source" in str(exc)
    else:
        raise AssertionError("incomplete FX evidence must be rejected")


def test_invalid_amount_currency_and_date_are_rejected(tmp_path):
    queue = FiscalPendingQueue(str(tmp_path / "fiscal.sqlite3"))
    for key, value in (("original_amount", 0), ("original_currency", "XYZ"), ("occurred_on", "30/10/2026")):
        payload = sample()
        payload[key] = value
        try:
            queue.add(payload)
        except ValueError:
            pass
        else:
            raise AssertionError(f"invalid {key} must be rejected")


def test_queue_is_separate_from_reserve_ledger(tmp_path):
    from finance.fiscal_reserve import FiscalReserve
    path = str(tmp_path / "fiscal.sqlite3")
    queue = FiscalPendingQueue(path)
    reserve = FiscalReserve(path)
    queue.add(sample())
    assert reserve.summary()["total_reserved_brl"] == 0
    assert reserve.summary()["periods"]["year"]["entries"] == 0


def test_pending_queue_pagination_returns_distinct_pages_and_total(tmp_path):
    queue = FiscalPendingQueue(str(tmp_path / "fiscal.sqlite3"))
    for number in range(7):
        queue.add(sample(f"FOREIGN-PAGE-{number}"))

    first = queue.list_pending(limit=3, offset=0)
    second = queue.list_pending(limit=3, offset=3)
    last = queue.list_pending(limit=3, offset=6)

    assert first["total"] == second["total"] == last["total"] == 7
    assert len(first["items"]) == 3
    assert len(second["items"]) == 3
    assert len(last["items"]) == 1
    references = [item["reference"] for page in (first, second, last) for item in page["items"]]
    assert len(references) == len(set(references)) == 7
    assert all(item["status"] == "PENDING_CLASSIFICATION" for page in (first, second, last) for item in page["items"])


def test_pending_queue_rejects_invalid_pagination(tmp_path):
    queue = FiscalPendingQueue(str(tmp_path / "fiscal.sqlite3"))
    for limit, offset in ((0, 0), (501, 0), (True, 0), (10, -1), (10, True)):
        try:
            queue.list_pending(limit=limit, offset=offset)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid pending pagination must be rejected")
