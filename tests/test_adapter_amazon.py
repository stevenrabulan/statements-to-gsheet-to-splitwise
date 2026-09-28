import json
from datetime import date
from pathlib import Path

import pytest

from adapters import amazon
from models import AccountConfig, ImporterError

FIXTURE = Path(__file__).parent / "fixtures" / "amazon-orders-sample.json"

AMAZON = AccountConfig("Amazon", date(2026, 7, 29))
ACCOUNTS = {
    "Chase4242": AccountConfig("Amazon Card"),
    "amazon-orders": AMAZON,
}


def _parse(path=FIXTURE, accounts=ACCOUNTS):
    return amazon.parse_orders(path, config=AMAZON, accounts=accounts)


def test_single_item_with_own_tax_becomes_one_row():
    result = _parse()
    assert len(result.transactions) == 1
    t = result.transactions[0]
    assert t.date == date(2026, 8, 3)
    assert t.description == "Fakebrand ForceFlex Trash Bags"
    assert t.amount == 14.07
    assert t.amount_formula == "=12.99+1.08"
    assert t.key == "amazon 111-0000000-0000001 #1"
    assert t.account == "Amazon Card"
    assert result.warnings == []


def _order(**overrides):
    """A single-Item Order in the scraped-file contract, with overrides."""
    item = {
        "position": 1, "title": "Fakebrand Widget, Blue, 2 Pack",
        "short_name": "Fakebrand Widget", "quantity": 1, "unit_price": 10.00,
        "cancelled": False, "tax": 0.83,
    }
    item.update(overrides.pop("item", {}))
    order = {
        "order_number": "111-0000000-0000009", "order_date": "2026-08-10",
        "status": "Delivered",
        "payment": [{"type": "card", "card_type": "Visa", "last_four": "4242"}],
        "order_total": 10.83, "shipping": 0, "discounts": [], "promos": [],
        "shipments": [{"shipped": True, "ship_date": "2026-08-11", "tax": 0.83,
                       "shipping": None, "items": [item]}],
    }
    order.update(overrides)
    return order


def _write(tmp_path, *orders, schema_version=1):
    f = tmp_path / "amazon-orders-2026-09-28.json"
    f.write_text(json.dumps({"schema_version": schema_version, "scraped_on": "2026-09-28",
                             "orders": list(orders), "refunds": []}))
    return f


def test_quantity_above_one_prefixes_name_and_multiplies_price(tmp_path):
    result = _parse(_write(tmp_path, _order(item={"quantity": 2, "unit_price": 12.99, "tax": 2.14})))
    t = result.transactions[0]
    assert t.description == "2× Fakebrand Widget"
    assert t.amount_formula == "=2*12.99+2.14"
    assert t.amount == 28.12


def test_zero_tax_is_left_out_of_the_formula(tmp_path):
    result = _parse(_write(tmp_path, _order(item={"unit_price": 4.50, "tax": 0})))
    t = result.transactions[0]
    assert t.amount_formula == "=4.5"
    assert t.amount == 4.50


@pytest.mark.parametrize("payment, label", [
    ([{"type": "gift_card"}], "Amazon Gift Card"),
    ([{"type": "points"}], "Points"),
    ([{"type": "gift_card"}, {"type": "card", "card_type": "Visa", "last_four": "4242"}],
     "Amazon Card"),
])
def test_payment_method_label(tmp_path, payment, label):
    result = _parse(_write(tmp_path, _order(payment=payment)))
    assert result.transactions[0].account == label
    assert result.warnings == []


def test_payment_method_never_changes_loaded_cost(tmp_path):
    card = _parse(_write(tmp_path, _order())).transactions[0]
    gift = _parse(_write(tmp_path, _order(payment=[{"type": "gift_card"}]))).transactions[0]
    assert (card.amount, card.amount_formula) == (gift.amount, gift.amount_formula)


def test_unmatched_card_falls_back_to_amazon_name_with_warning(tmp_path):
    order = _order(payment=[{"type": "card", "card_type": "Visa", "last_four": "9999"}])
    result = _parse(_write(tmp_path, order))
    assert result.transactions[0].account == "Amazon"
    assert len(result.warnings) == 1
    assert "111-0000000-0000009" in result.warnings[0]
    assert "9999" in result.warnings[0]


def test_wrong_schema_version_fails_loudly(tmp_path):
    with pytest.raises(ImporterError, match="schema_version"):
        _parse(_write(tmp_path, _order(), schema_version=2))


def test_missing_field_names_the_order(tmp_path):
    order = _order()
    del order["order_date"]
    with pytest.raises(ImporterError, match="111-0000000-0000009.*order_date"):
        _parse(_write(tmp_path, order))


def test_order_needing_cost_allocation_is_skipped_not_guessed(tmp_path):
    # Shipment tax with no per-Item tax needs the allocation math, so the
    # Order is held back rather than written with a wrong Amount.
    result = _parse(_write(tmp_path, _order(item={"tax": None})))
    assert result.transactions == []
    assert result.skipped["needs cost allocation"] == 1
    assert "111-0000000-0000009" in result.warnings[0]
