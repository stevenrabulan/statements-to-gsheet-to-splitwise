from datetime import date

import pytest

from models import ImporterError, Transaction
from dedup import dedup, existing_keys_from_rows, _coerce_date, _coerce_amount


def _t(amount, desc="Coffee", d=date(2026, 6, 1), account="Visa"):
    return Transaction(date=d, description=desc, amount=amount, account=account)


def _row(date_str, amount, desc, account):
    # Sheet row layout: A=date B=amount C=desc D E F G=account
    return [date_str, amount, desc, "", True, "", account]


def test_exact_reimport_adds_nothing():
    existing = existing_keys_from_rows([_row("06/01/2026", "5.00", "Coffee", "Visa")])
    assert dedup([_t(5.00)], existing) == []


def test_true_repeat_charge_preserved():
    # Two identical coffees, none in the sheet yet -> both kept.
    assert len(dedup([_t(5.00), _t(5.00)], existing_keys_from_rows([]))) == 2


def test_partial_overlap_sheet_has_one_batch_has_two():
    existing = existing_keys_from_rows([_row("06/01/2026", "5.00", "Coffee", "Visa")])
    kept = dedup([_t(5.00), _t(5.00)], existing)
    assert len(kept) == 1


def test_normalization_matches_case_and_whitespace():
    existing = existing_keys_from_rows([_row("06/01/2026", "$5.00", "  coffee   SHOP ", "  visa ")])
    assert dedup([_t(5.00, desc="Coffee Shop", account="Visa")], existing) == []


def test_unparseable_existing_rows_ignored():
    rows = [["header", "Amount", "Desc"], ["", "", ""], _row("06/01/2026", "5.00", "Coffee", "Visa")]
    existing = existing_keys_from_rows(rows)
    # The junk rows don't crash and only the one valid row is counted:
    assert sum(existing.values()) == 1
    assert dedup([_t(5.00)], existing) == []                 # matches the one valid row
    new = dedup([_t(9.99, desc="New")], existing)            # no match -> kept
    assert len(new) == 1 and new[0].description == "New"


# --- sheet cell coercion -------------------------------------------------
# The live sheet returns UNFORMATTED_VALUE: date serials and float amounts.

def test_serial_date_matches_google_epoch():
    assert _coerce_date(46123) == date(2026, 4, 11)          # observed in the real sheet
    assert _coerce_date(1) == date(1899, 12, 31)


def test_text_dates_accept_both_layouts():
    """A date column displayed as YYYY/MM/DD must still parse."""
    assert _coerce_date("06/01/2026") == date(2026, 6, 1)
    assert _coerce_date("2026/06/01") == date(2026, 6, 1)
    assert _coerce_date("2026-06-01") == date(2026, 6, 1)


def test_out_of_range_serial_rejected():
    with pytest.raises(ValueError):
        _coerce_date(0)
    with pytest.raises(ValueError):
        _coerce_date(10_000_000)


def test_booleans_are_not_dates_or_amounts():
    with pytest.raises(ValueError):
        _coerce_date(True)
    with pytest.raises(ValueError):
        _coerce_amount(True)


def test_amount_accepts_float_and_currency_text():
    assert _coerce_amount(104.87) == 104.87
    assert _coerce_amount("$1,234.56") == 1234.56
    assert _coerce_amount("(5.00)") == -5.00
    assert _coerce_amount("-5.44") == -5.44


def test_unformatted_sheet_rows_dedup_correctly():
    """Regression: serial-date rows from the sheet must match parsed transactions."""
    existing = existing_keys_from_rows([_row(46123, 104.87, "FakeMart CURBSIDE", "FakeMart Card")])
    txn = _t(104.87, desc="FakeMart CURBSIDE", d=date(2026, 4, 11), account="FakeMart Card")
    assert dedup([txn], existing) == []


def test_all_rows_unparseable_raises_instead_of_duplicating():
    """A wholesale parse failure previously returned an empty Counter, marking
    every incoming row as new and duplicating the entire import."""
    rows = [["2026/06/01", "junk", "Desc", "", True, "", "Visa"] for _ in range(12)]
    with pytest.raises(ImporterError, match="refusing to import"):
        existing_keys_from_rows(rows)


def test_small_unparseable_sheet_does_not_raise():
    """Below the sanity threshold, a zero result is normal (fixtures, new sheets)."""
    assert existing_keys_from_rows([["header", "Amount"]]) == {}
    assert existing_keys_from_rows([]) == {}


def test_blank_rows_do_not_count_toward_sanity_threshold():
    rows = [["", "", ""] for _ in range(50)]
    assert existing_keys_from_rows(rows) == {}
