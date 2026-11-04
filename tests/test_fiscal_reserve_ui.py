from pathlib import Path


RESERVE_PAGE = Path(__file__).resolve().parents[1] / "web" / "fiscal-reserve.html"


def test_foreign_review_ui_uses_only_the_foreign_classification_catalog():
    source = RESERVE_PAGE.read_text(encoding="utf-8")

    assert '<select id="reviewClassification" required>' in source
    assert 'value="FOREIGN_FINANCIAL_INVESTMENT"' in source
    assert 'value="FOREIGN_ENTITY_CONTROLLED"' in source
    assert 'value="FOREIGN_CRYPTO"' in source
    assert '<input id="reviewClassification"' not in source
    assert 'value="BR_DAY_TRADE"' not in source
