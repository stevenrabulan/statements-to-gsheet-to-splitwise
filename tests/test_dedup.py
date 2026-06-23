from datetime import date

from models import Transaction
from dedup import dedup, existing_keys_from_rows


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
