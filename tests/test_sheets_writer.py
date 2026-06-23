from datetime import date
from models import Transaction
from sheets_writer import build_row


def _txn(**kw):
    base = dict(date=date(2026, 5, 20), description="WHOLE FOODS MARKET",
                amount=45.67, account="Chase Sapphire Reserve",
                source_file="Chase Sapphire Reserve.csv")
    base.update(kw)
    return Transaction(**base)


def test_build_row_fields():
    row = build_row(_txn())
    assert row[0] == "05/20/2026"
    assert row[1] == 45.67
    assert row[2] == "WHOLE FOODS MARKET"
    assert row[3] == ""
    assert row[4] is True
    assert row[5] == ""
    assert row[6] == "Chase Sapphire Reserve"
    assert row[7] == "" and row[8] == "" and row[9] == ""
    assert row[10] == "split-transactions automation Chase Sapphire Reserve.csv"
    assert len(row) == 11


def test_build_row_date_format():
    row = build_row(_txn(date=date(2026, 1, 5)))
    assert row[0] == "01/05/2026"


def test_k_note_falls_back_when_source_file_empty():
    row = build_row(_txn(source_file=""))
    assert row[10] == "split-transactions automation"
