from pathlib import Path
from datetime import date

import pytest

from csv_reader import read_csv
from models import ImporterError
from adapters import chase_credit, detect_adapter

FIXTURE = Path(__file__).parent / "fixtures" / "chase_credit_sample.csv"


def _parse():
    header, rows = read_csv(FIXTURE)
    assert chase_credit.matches(header)
    return chase_credit.parse(rows, account="Chase Sapphire Reserve")


def test_keeps_sales_normalized_to_positive():
    result = _parse()
    sales = [t for t in result.transactions if t.description != "FAKE STORE RETURN"]
    assert len(sales) == 2
    assert all(t.amount > 0 for t in sales)
    t = next(t for t in result.transactions if t.description == "FAKE GAS STATION")
    assert t.date == date(2026, 4, 30)
    assert t.amount == 44.57
    assert t.account == "Chase Sapphire Reserve"


def test_returns_imported_as_negative():
    result = _parse()
    t = next(t for t in result.transactions if t.description == "FAKE STORE RETURN")
    assert t.amount == -12.00
    assert t.date == date(2026, 5, 2)


def test_non_sale_types_dropped_by_reason():
    result = _parse()
    assert result.skipped["payment/deposit"] == 1     # Payment
    assert result.skipped["credit/refund"] == 2       # Fee + Adjustment


def test_routes_by_header():
    header, _ = read_csv(FIXTURE)
    assert detect_adapter(header).NAME == "chase-credit"


def test_missing_column_raises():
    with pytest.raises(ImporterError):
        chase_credit.parse([{"Transaction Date": "05/04/2026"}], account="X")
