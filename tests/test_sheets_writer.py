from unittest.mock import MagicMock, patch
from datetime import date
from pdf_parser import Transaction
from sheets_writer import build_row, get_sheet_name

def test_build_row():
    txn = Transaction(
        date=date(2026, 5, 20),
        description="WHOLE FOODS MARKET",
        amount=45.67,
        card_name="Chase Sapphire",
    )
    row = build_row(txn)
    assert row[0] == "05/20/2026"
    assert row[1] == 45.67
    assert row[2] == "WHOLE FOODS MARKET"
    assert row[3] == ""
    assert row[4] is True
    assert row[5] == ""
    assert row[6] == "Chase Sapphire"
    assert row[7] == ""
    assert row[8] == ""
    assert row[9] == ""
    assert row[10] == "Automated by Claude"
    assert len(row) == 11

def test_build_row_date_format():
    txn = Transaction(date=date(2026, 1, 5), description="X", amount=1.0, card_name="Y")
    row = build_row(txn)
    assert row[0] == "01/05/2026"
