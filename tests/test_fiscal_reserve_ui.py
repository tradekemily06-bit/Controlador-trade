from pathlib import Path


RESERVE_PAGE = Path(__file__).resolve().parents[1] / "web" / "fiscal-reserve.html"


def test_foreign_review_ui_uses_only_the_foreign_classification_catalog():
    source = RESERVE_PAGE.read_text(encoding="utf-8")
    review_form = source.split('<form id="reviewForm"', 1)[1].split("</form>", 1)[0]

    assert '<select id="reviewClassification" required>' in review_form
    assert 'value="FOREIGN_FINANCIAL_INVESTMENT"' in review_form
    assert 'value="FOREIGN_ENTITY_CONTROLLED"' in review_form
    assert 'value="FOREIGN_CRYPTO"' in review_form
    assert '<input id="reviewClassification"' not in review_form
    assert 'value="BR_DAY_TRADE"' not in review_form
