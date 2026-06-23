from pathlib import Path
from datetime import date

import pytest

from csv_reader import read_csv
from models import ImporterError
from adapters import discover, detect_adapter

FIXTURE = Path(__file__).parent / "fixtures" / "discover_sample.csv"


def _parse():
    header, rows = read_csv(FIXTURE)
    assert discover.matches(header)
    return discover.parse(rows, account="Discover Card")


def test_keeps_purchases_positive():
    result = _parse()
    assert len(result.transactions) == 2
    assert all(t.amount > 0 for t in result.transactions)
    t = result.transactions[0]
    assert t.date == date(2026, 4, 15)
    assert t.description == "FAKE DINER"
    assert t.amount == 18.38
    assert t.account == "Discover Card"


def test_payments_and_negative_amounts_dropped():
    result = _parse()
    assert result.skipped["credit/refund"] == 2
    descriptions = [t.description for t in result.transactions]
    assert "PAYMENT THANK YOU" not in descriptions
    assert "FAKE STORE REFUND" not in descriptions


def test_routes_by_header():
    header, _ = read_csv(FIXTURE)
    assert detect_adapter(header).NAME == "discover"


def test_missing_column_raises():
    with pytest.raises(ImporterError):
        discover.parse([{"Trans. Date": "04/15/2026"}], account="Discover Card")
