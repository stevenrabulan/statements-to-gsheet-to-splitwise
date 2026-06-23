from pathlib import Path
from datetime import date

import pytest

from csv_reader import read_csv, read_csv_text
from models import ImporterError
from adapters import fakecoin

FIXTURE = Path(__file__).parent / "fixtures" / "fakecoin_sample.csv"


def _parse():
    header, rows = read_csv(FIXTURE)
    assert fakecoin.matches(header)
    return fakecoin.parse(rows, account="Fakecoin Card")


def test_keeps_only_purchases_and_normalizes_fields():
    result = _parse()
    assert len(result.transactions) == 2
    t = result.transactions[0]
    assert t.date == date(2026, 6, 1)
    assert t.description == "WHOLE FOODS"
    assert t.amount == 12.50
    assert t.account == "Fakecoin Card"


def test_payment_and_dead_status_dropped():
    result = _parse()
    assert result.skipped["payment/deposit"] == 1
    assert result.skipped["dead status"] == 1


def test_unknown_status_imported_with_warning():
    result = _parse()
    descriptions = [t.description for t in result.transactions]
    assert "COFFEE BAR" in descriptions
    assert len(result.warnings) == 1
    assert "PENDING_REVIEW" in result.warnings[0]


def test_matches_rejects_foreign_header():
    assert fakecoin.matches(["Trans. Date", "Post Date", "Description", "Amount", "Category"]) is False


def test_tab_delimited_parses():
    text = FIXTURE.read_text().replace(",", "\t")
    header, rows = read_csv_text(text)
    result = fakecoin.parse(rows, account="Fakecoin Card")
    assert len(result.transactions) == 2


def test_missing_column_raises():
    rows = [{"Date": "2026-06-01", "Amount": "5.00"}]
    with pytest.raises(ImporterError):
        fakecoin.parse(rows, account="Fakecoin Card")
