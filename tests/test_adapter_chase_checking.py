from pathlib import Path
from datetime import date

import pytest

from csv_reader import read_csv
from models import ImporterError
from adapters import chase_checking, chase_credit, detect_adapter

FIXTURE = Path(__file__).parent / "fixtures" / "chase_checking_sample.csv"


def _parse():
    header, rows = read_csv(FIXTURE)
    assert chase_checking.matches(header)
    return chase_checking.parse(rows, account="Chase Checking")


def test_keeps_only_everyday_spending_positive():
    result = _parse()
    descs = sorted(t.description for t in result.transactions)
    assert descs == ["ATT PAYMENT PPD ID: 9864031004", "FAKE GROCERY STORE",
                     "FAKE UTILITY CO UTILITY PAYMENT"]
    assert all(t.amount > 0 for t in result.transactions)
    g = next(t for t in result.transactions if t.description == "FAKE GROCERY STORE")
    assert g.date == date(2026, 6, 15) and g.amount == 52.10 and g.account == "Chase Checking"


def test_card_payments_excluded():
    result = _parse()
    assert result.skipped["card payment"] == 4
    joined = " ".join(t.description.upper() for t in result.transactions)
    assert "FAKECOIN CARD" not in joined and "E-PAYMENT" not in joined and "FAKECARD" not in joined


def test_att_bill_not_treated_as_card_payment():
    # "ATT PAYMENT" contains the word PAYMENT but is a bill, must be kept.
    result = _parse()
    assert any(t.description.startswith("ATT PAYMENT") for t in result.transactions)


def test_transfers_and_money_in_excluded():
    result = _parse()
    assert result.skipped["transfer"] == 1
    assert result.skipped["deposit/credit"] == 3


def test_atm_and_crypto_excluded():
    result = _parse()
    assert result.skipped["atm/cash"] == 2
    assert result.skipped["crypto"] == 2


def test_routes_distinctly_from_chase_credit():
    header, _ = read_csv(FIXTURE)
    assert detect_adapter(header).NAME == "chase-checking"
    # And the credit header must NOT route to checking:
    assert not chase_checking.matches(["Transaction Date", "Post Date", "Description",
                                       "Category", "Type", "Amount", "Memo"])
    assert not chase_credit.matches(header)


def test_missing_column_raises():
    with pytest.raises(ImporterError):
        chase_checking.parse([{"Details": "DEBIT"}], account="Chase Checking")
