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
    result = _parse(_write(tmp_path, _order(order_total=28.12, item={"quantity": 2, "unit_price": 12.99, "tax": 2.14})))
    t = result.transactions[0]
    assert t.description == "2× Fakebrand Widget"
    assert t.amount_formula == "=2*12.99+2.14"
    assert t.amount == 28.12


def test_zero_tax_is_left_out_of_the_formula(tmp_path):
    result = _parse(_write(tmp_path, _order(order_total=4.50, item={"unit_price": 4.50, "tax": 0})))
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


def _item(position, unit_price, quantity=1, tax=None, cancelled=False):
    return {"position": position, "title": f"Fakebrand Thing {position}",
            "short_name": f"Thing {position}", "quantity": quantity,
            "unit_price": unit_price, "cancelled": cancelled, "tax": tax}


def _shipment(*items, tax=0, shipping=None):
    return {"shipped": True, "ship_date": "2026-08-11", "tax": tax,
            "shipping": shipping, "items": list(items)}


def _multi(order_total, *shipments, **overrides):
    return _order(order_total=order_total, shipments=list(shipments), **overrides)


def _rows(tmp_path, order):
    result = _parse(_write(tmp_path, order))
    return result, {t.key.rsplit("#", 1)[1]: t for t in result.transactions}


def test_shipment_tax_is_spread_by_net_price(tmp_path):
    # tax 1.00 over 30.00 / 10.00 -> 0.75 / 0.25
    order = _multi(41.00, _shipment(_item(1, 30.00), _item(2, 10.00), tax=1.00))
    result, rows = _rows(tmp_path, order)
    assert rows["1"].amount_formula == "=30+0.75"
    assert rows["2"].amount_formula == "=10+0.25"
    assert result.warnings == []


def test_single_item_shipment_takes_its_tax_exactly(tmp_path):
    result, rows = _rows(tmp_path, _multi(10.83, _shipment(_item(1, 10.00), tax=0.83)))
    assert rows["1"].amount_formula == "=10+0.83"


def test_own_tax_wins_and_shipment_tax_remainder_goes_to_the_rest(tmp_path):
    order = _multi(22.00, _shipment(_item(1, 10.00, tax=0.50), _item(2, 10.00), tax=2.00))
    _, rows = _rows(tmp_path, order)
    assert rows["1"].amount_formula == "=10+0.5"
    assert rows["2"].amount_formula == "=10+1.5"


def test_promo_on_one_item_reduces_only_that_item(tmp_path):
    order = _multi(17.00, _shipment(_item(1, 10.00, tax=0), _item(2, 10.00, tax=0)),
                   promos=[{"name": "Save $3", "amount": 3.00, "positions": [1]}])
    _, rows = _rows(tmp_path, order)
    assert rows["1"].amount_formula == "=10-3"
    assert rows["1"].amount == 7.00
    assert rows["2"].amount_formula == "=10"


def test_promo_on_several_items_spreads_by_line_price(tmp_path):
    # line prices 2*10=20 and 10 -> $3 splits 2.00 / 1.00
    order = _multi(27.00, _shipment(_item(1, 10.00, quantity=2, tax=0), _item(2, 10.00, tax=0)),
                   promos=[{"name": "Save $3", "amount": 3.00, "positions": [1, 2]}])
    _, rows = _rows(tmp_path, order)
    assert rows["1"].amount_formula == "=2*10-2"
    assert rows["2"].amount_formula == "=10-1"


def test_tax_is_spread_by_price_after_promos(tmp_path):
    # net 10 and 5 after a $5 promo on #2 -> tax 0.30 splits 0.20 / 0.10
    order = _multi(15.30, _shipment(_item(1, 10.00), _item(2, 10.00), tax=0.30),
                   promos=[{"name": "Save $5", "amount": 5.00, "positions": [2]}])
    _, rows = _rows(tmp_path, order)
    assert rows["1"].amount_formula == "=10+0.2"
    assert rows["2"].amount_formula == "=10-5+0.1"


def test_shipping_and_whole_order_discount_spread_by_net_price(tmp_path):
    order = _multi(44.00, _shipment(_item(1, 30.00, tax=0), _item(2, 10.00, tax=0)),
                   shipping=8.00, discounts=[{"name": "Order discount", "amount": 4.00}])
    _, rows = _rows(tmp_path, order)
    # shipping 8 -> 6 / 2, discount 4 -> 3 / 1; discount is a subtraction, last
    assert rows["1"].amount_formula == "=30+6-3"
    assert rows["2"].amount_formula == "=10+2-1"
    assert rows["1"].amount == 33.00


def test_shipment_shipping_spreads_only_over_its_shipment(tmp_path):
    order = _multi(25.00,
                   _shipment(_item(1, 10.00, tax=0), _item(2, 10.00, tax=0), shipping=4.00),
                   _shipment(_item(3, 1.00, tax=0)))
    _, rows = _rows(tmp_path, order)
    assert rows["1"].amount_formula == "=10+2"
    assert rows["2"].amount_formula == "=10+2"
    assert rows["3"].amount_formula == "=1"


def test_formula_term_order_is_fixed(tmp_path):
    order = _multi(15.80, _shipment(_item(1, 10.00, quantity=2, tax=1.00)),
                   shipping=1.50, discounts=[{"name": "d", "amount": 0.70}],
                   promos=[{"name": "p", "amount": 6.00, "positions": [1]}])
    _, rows = _rows(tmp_path, order)
    assert rows["1"].amount_formula == "=2*10-6+1+1.5-0.7"
    assert rows["1"].amount == 15.80


def test_rounding_remainder_goes_to_the_largest_part(tmp_path):
    # $1.00 shipping over three equal Items: 0.33 each, leftover cent to the first largest
    order = _multi(31.00, _shipment(_item(1, 10.00, tax=0), _item(2, 10.00, tax=0),
                                    _item(3, 10.00, tax=0)), shipping=1.00)
    _, rows = _rows(tmp_path, order)
    assert sorted(t.amount for t in rows.values()) == [10.33, 10.33, 10.34]
    assert sum(t.amount for t in rows.values()) == pytest.approx(31.00)


def test_leftover_cent_lands_on_the_larger_item(tmp_path):
    # $0.01 shipping over 20 and 10: 0.0067 / 0.0033 round to 0.01 / 0.00
    order = _multi(30.01, _shipment(_item(1, 20.00, tax=0), _item(2, 10.00, tax=0)),
                   shipping=0.01)
    _, rows = _rows(tmp_path, order)
    assert rows["1"].amount_formula == "=20+0.01"
    assert rows["2"].amount_formula == "=10"


def test_total_mismatch_skips_the_whole_order_with_a_warning(tmp_path):
    order = _multi(99.99, _shipment(_item(1, 10.00, tax=0), _item(2, 10.00, tax=0)))
    result = _parse(_write(tmp_path, order))
    assert result.transactions == []
    assert result.skipped["total mismatch"] == 2
    warning = result.warnings[0]
    assert "111-0000000-0000009" in warning
    assert "99.99" in warning and "20.00" in warning


def test_gift_card_payment_does_not_change_the_math(tmp_path):
    order = _multi(41.00, _shipment(_item(1, 30.00), _item(2, 10.00), tax=1.00),
                   payment=[{"type": "gift_card"}])
    result, rows = _rows(tmp_path, order)
    assert rows["1"].amount_formula == "=30+0.75"
    assert result.skipped["total mismatch"] == 0


# --- readiness, cancelled Items, ship-date cutoff -------------------------------

def _shipment_on(ship_date, *items, shipped=True, tax=0):
    return {"shipped": shipped, "ship_date": ship_date if shipped else None,
            "tax": tax, "shipping": None, "items": list(items)}


def test_order_with_an_unshipped_shipment_is_held_as_not_ready(tmp_path):
    order = _multi(20.00,
                   _shipment_on("2026-08-11", _item(1, 10.00, tax=0)),
                   _shipment_on(None, _item(2, 10.00, tax=0), shipped=False))
    result = _parse(_write(tmp_path, order))
    assert result.transactions == []
    assert result.skipped["not ready"] == 2


def test_cancelled_item_in_unshipped_shipment_does_not_block_the_order(tmp_path):
    order = _multi(10.00,
                   _shipment_on("2026-08-11", _item(1, 10.00, tax=0)),
                   _shipment_on(None, _item(2, 99.00, cancelled=True), shipped=False))
    result, rows = _rows(tmp_path, order)
    assert list(rows) == ["1"]
    assert result.skipped["not ready"] == 0


def test_cancelled_item_plays_no_part_in_tax_spread_or_total_check(tmp_path):
    order = _multi(21.00,
                   _shipment_on("2026-08-11", _item(1, 20.00), _item(2, 50.00, cancelled=True),
                                tax=1.00))
    result, rows = _rows(tmp_path, order)
    assert list(rows) == ["1"]
    assert rows["1"].amount == 21.00
    assert result.warnings == []


def test_item_shipped_before_the_cutoff_is_skipped_and_counted(tmp_path):
    order = _multi(10.00, _shipment_on("2026-07-28", _item(1, 10.00, tax=0)))
    result = _parse(_write(tmp_path, order))
    assert result.transactions == []
    assert result.skipped["before 2026-07-29"] == 1


def test_item_shipped_on_the_cutoff_day_is_imported(tmp_path):
    order = _multi(10.00, _shipment_on("2026-07-29", _item(1, 10.00, tax=0)))
    _, rows = _rows(tmp_path, order)
    assert list(rows) == ["1"]


def test_order_placed_before_the_cutoff_but_shipped_after_is_imported(tmp_path):
    order = _multi(10.00, _shipment_on("2026-07-30", _item(1, 10.00, tax=0)),
                   order_date="2026-07-25")
    _, rows = _rows(tmp_path, order)
    assert list(rows) == ["1"]


def test_cutoff_is_per_shipment_and_total_check_still_covers_the_whole_order(tmp_path):
    order = _multi(20.00,
                   _shipment_on("2026-07-20", _item(1, 10.00, tax=0)),
                   _shipment_on("2026-08-02", _item(2, 10.00, tax=0)))
    result, rows = _rows(tmp_path, order)
    assert list(rows) == ["2"]
    assert result.skipped["before 2026-07-29"] == 1
    assert result.warnings == []


def test_no_cutoff_configured_imports_everything(tmp_path):
    order = _multi(10.00, _shipment_on("2020-01-01", _item(1, 10.00, tax=0)))
    result = amazon.parse_orders(_write(tmp_path, order), config=AccountConfig("Amazon"),
                                 accounts=ACCOUNTS)
    assert len(result.transactions) == 1
