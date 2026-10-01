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
        "kind": "physical",
        "order_number": "111-0000000-0000009", "order_date": "2026-08-10",
        "status": "Delivered",
        "payment": [{"type": "card", "card_type": "Visa", "last_four": "4242"}],
        "order_total": 10.83, "tax": None, "shipping": 0, "discounts": [], "promos": [],
        "shipments": [{"shipped": True, "ship_date": "2026-08-11", "tax": 0.83,
                       "shipping": None, "items": [item]}],
    }
    order.update(overrides)
    return order


def _write(tmp_path, *orders, schema_version=2, refunds=()):
    f = tmp_path / "amazon-orders-2026-09-28.json"
    f.write_text(json.dumps({"schema_version": schema_version, "scraped_on": "2026-09-28",
                             "orders": list(orders), "refunds": list(refunds)}))
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


@pytest.mark.parametrize("version", [1, 3, None])
def test_only_schema_version_2_is_accepted(tmp_path, version):
    with pytest.raises(ImporterError, match="schema_version.*expected 2"):
        _parse(_write(tmp_path, _order(), schema_version=version))


def test_missing_kind_names_the_order(tmp_path):
    order = _order()
    del order["kind"]
    with pytest.raises(ImporterError, match="111-0000000-0000009.*kind"):
        _parse(_write(tmp_path, order))


@pytest.mark.parametrize("kind", ["grocery", "", 7, None])
def test_unknown_kind_names_the_order(tmp_path, kind):
    with pytest.raises(ImporterError, match="111-0000000-0000009.*kind"):
        _parse(_write(tmp_path, _order(kind=kind)))


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


def test_small_amount_over_many_items_never_goes_negative(tmp_path):
    # $0.05 over seven equal Items: five get a cent, two get nothing
    items = [_item(n, 1.00) for n in range(1, 8)]
    order = _multi(7.05, _shipment(*items, tax=None), tax=0.05)
    result, rows = _rows(tmp_path, order)
    assert [rows[str(n)].amount_formula for n in range(1, 8)] == ["=1+0.01"] * 5 + ["=1"] * 2
    assert result.warnings == []


def test_leftover_cents_go_to_the_parts_cut_off_the_most(tmp_path):
    # $0.05 over 1/1/1/1/1/1/1/2: exact shares 0.0056 x7 and 0.0111. The $2 Item
    # keeps its whole cent and the other four cents go to the first four Items.
    items = [_item(n, 1.00) for n in range(1, 8)] + [_item(8, 2.00)]
    order = _multi(9.05, _shipment(*items, tax=None), tax=0.05)
    _, rows = _rows(tmp_path, order)
    assert [rows[str(n)].amount for n in range(1, 9)] == [1.01] * 4 + [1.00] * 3 + [2.01]


def test_equal_items_split_an_odd_cent_with_the_extra_on_the_first(tmp_path):
    order = _multi(20.03, _shipment(_item(1, 10.00), _item(2, 10.00), tax=None), tax=0.03)
    _, rows = _rows(tmp_path, order)
    assert rows["1"].amount_formula == "=10+0.02"
    assert rows["2"].amount_formula == "=10+0.01"


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


# --- Digital Orders --------------------------------------------------------------

DIGITAL_NUMBER = "D01-0000000-0000050"


def _digital(**overrides):
    order = {
        "kind": "digital", "order_number": DIGITAL_NUMBER, "charge_date": "2026-09-09",
        "short_name": "Grocery Subscription",
        "payment": [{"type": "card", "card_type": "Visa", "last_four": "4242"}],
        "order_total": 9.99,
    }
    order.update(overrides)
    return order


def test_digital_order_is_one_plain_amount_row_dated_when_charged(tmp_path):
    result = _parse(_write(tmp_path, _digital()))
    [t] = result.transactions
    assert t.date == date(2026, 9, 9)
    assert t.description == "Grocery Subscription"
    assert t.amount == 9.99
    assert t.amount_formula is None
    assert t.key == f"amazon {DIGITAL_NUMBER}"
    assert t.account == "Amazon Card"
    assert t.refunds is None and t.note_suffix == ""
    assert result.warnings == []


def test_digital_order_cutoff_compares_the_charge_date(tmp_path):
    before = _digital(charge_date="2026-07-28")
    on = _digital(charge_date="2026-07-29", order_number="D01-0000000-0000051")
    result = _parse(_write(tmp_path, before, on))
    assert [t.key for t in result.transactions] == ["amazon D01-0000000-0000051"]
    assert result.skipped["before 2026-07-29"] == 1
    assert result.warnings == []


def test_digital_order_payment_method_follows_the_same_rules_as_items(tmp_path):
    gift = _digital(payment=[{"type": "gift_card"}])
    [t] = _parse(_write(tmp_path, gift)).transactions
    assert t.account == "Amazon Gift Card"
    odd = _digital(payment=[{"type": "card", "card_type": "Visa", "last_four": "9999"}])
    result = _parse(_write(tmp_path, odd))
    assert result.transactions[0].account == "Amazon"
    assert "9999" in result.warnings[0]


@pytest.mark.parametrize("field, value", [
    ("charge_date", None), ("charge_date", "09/09/2026"), ("short_name", ""),
    ("short_name", None), ("order_total", None), ("order_total", 9.999), ("order_total", "9.99"),
    ("payment", []),
])
def test_digital_order_bad_fields_fail_loudly_naming_the_order(tmp_path, field, value):
    with pytest.raises(ImporterError, match=DIGITAL_NUMBER):
        _parse(_write(tmp_path, _digital(**{field: value})))


def test_digital_order_is_not_held_for_shipping_and_needs_no_order_date(tmp_path):
    order = _digital()
    assert "order_date" not in order and "shipments" not in order
    assert len(_parse(_write(tmp_path, order)).transactions) == 1


def test_refund_on_a_digital_order_is_skipped_with_a_warning(tmp_path):
    result = _parse(_write(tmp_path, _digital(),
                           refunds=[_refund(4.99, order_number=DIGITAL_NUMBER, positions=[])]))
    assert [t.key for t in result.transactions] == [f"amazon {DIGITAL_NUMBER}"]
    assert result.skipped["refund on Digital Order"] == 1
    [warning] = result.warnings
    assert DIGITAL_NUMBER in warning and "4.99" in warning
    assert "Digital Order" in warning and "by hand" in warning


# --- Whole Foods Orders ----------------------------------------------------------

WF_NUMBER = "111-0000000-0000060"


def _whole_foods(**overrides):
    order = {
        "kind": "whole_foods", "order_number": WF_NUMBER, "order_date": "2026-09-11",
        "delivered": True,
        "payment": [{"type": "card", "card_type": "Visa", "last_four": "4242"}],
        "order_total": 113.99,
        "additions": [{"name": "Subtotal", "amount": 106.99},
                    {"name": "Driver tip", "amount": 7.00}],
        "discounts": [],
    }
    order.update(overrides)
    return order


def test_whole_foods_order_is_one_row_for_the_whole_order(tmp_path):
    result = _parse(_write(tmp_path, _whole_foods()))
    [t] = result.transactions
    assert t.date == date(2026, 9, 11)
    assert t.description == "Whole Foods"
    assert t.amount == 113.99
    assert t.amount_formula == "=106.99+7"
    assert t.key == f"amazon {WF_NUMBER}"
    assert t.account == "Amazon Card"
    assert t.refunds is None
    assert result.warnings == []


def test_whole_foods_discounts_are_subtracted_after_the_additions(tmp_path):
    order = _whole_foods(order_total=110.49,
                         additions=[{"name": "Subtotal", "amount": 106.99},
                                  {"name": "Driver tip", "amount": 7.00},
                                  {"name": "Bag fee", "amount": 0.50}],
                         discounts=[{"name": "Promotion", "amount": 4.00}])
    [t] = _parse(_write(tmp_path, order)).transactions
    assert t.amount_formula == "=106.99+7+0.5-4"
    assert t.amount == 110.49


def test_whole_foods_total_mismatch_skips_the_order_with_a_warning(tmp_path):
    result = _parse(_write(tmp_path, _whole_foods(order_total=114.99)))
    assert result.transactions == []
    assert result.skipped["total mismatch"] == 1
    [warning] = result.warnings
    assert WF_NUMBER in warning and "114.99" in warning and "113.99" in warning


def test_whole_foods_order_not_delivered_is_held_as_not_ready(tmp_path):
    result = _parse(_write(tmp_path, _whole_foods(delivered=False)))
    assert result.transactions == []
    assert result.skipped["not ready"] == 1
    assert result.warnings == []


def test_whole_foods_cutoff_compares_the_order_date(tmp_path):
    before = _whole_foods(order_date="2026-07-28")
    on = _whole_foods(order_date="2026-07-29", order_number="111-0000000-0000061")
    result = _parse(_write(tmp_path, before, on))
    assert [t.key for t in result.transactions] == ["amazon 111-0000000-0000061"]
    assert result.skipped["before 2026-07-29"] == 1


def test_whole_foods_order_before_the_cutoff_is_ignored_even_if_totals_disagree(tmp_path):
    result = _parse(_write(tmp_path, _whole_foods(order_date="2026-07-01", order_total=1.00)))
    assert result.transactions == []
    assert result.skipped["before 2026-07-29"] == 1
    assert result.skipped["total mismatch"] == 0
    assert result.warnings == []


def test_whole_foods_payment_method_follows_the_same_rules_as_items(tmp_path):
    gift = _whole_foods(payment=[{"type": "gift_card"}])
    [t] = _parse(_write(tmp_path, gift)).transactions
    assert t.account == "Amazon Gift Card"
    odd = _whole_foods(payment=[{"type": "card", "card_type": "Visa", "last_four": "9999"}])
    result = _parse(_write(tmp_path, odd))
    assert result.transactions[0].account == "Amazon"
    assert "9999" in result.warnings[0]


@pytest.mark.parametrize("field, value", [("additions", []), ("delivered", "yes"),
                                          ("discounts", None)])
def test_whole_foods_bad_fields_fail_loudly_naming_the_order(tmp_path, field, value):
    with pytest.raises(ImporterError, match=WF_NUMBER):
        _parse(_write(tmp_path, _whole_foods(**{field: value})))


def test_whole_foods_refund_is_one_negative_row_against_the_order(tmp_path):
    result = _parse(_write(tmp_path, _whole_foods(),
                           refunds=[_refund(4.99, "2026-09-12", WF_NUMBER, positions=())]))
    [refund] = _refund_rows(result)
    assert refund.date == date(2026, 9, 12)
    assert refund.amount == -4.99
    assert refund.amount_formula is None
    assert refund.description == "Refund: Whole Foods"
    assert refund.account == "Amazon Card"
    assert refund.key == f"amazon {WF_NUMBER} refund 2026-09-12 4.99"
    assert refund.refunds == f"amazon {WF_NUMBER}"
    assert result.warnings == []


def test_whole_foods_refund_is_imported_even_if_the_order_is_not_delivered(tmp_path):
    result = _parse(_write(tmp_path, _whole_foods(delivered=False),
                           refunds=[_refund(4.99, "2026-09-12", WF_NUMBER, positions=())]))
    assert [t.refunds for t in result.transactions] == [f"amazon {WF_NUMBER}"]


def test_whole_foods_refund_on_an_order_before_the_cutoff_is_skipped_with_a_warning(tmp_path):
    result = _parse(_write(tmp_path, _whole_foods(order_date="2026-07-20"),
                           refunds=[_refund(4.99, "2026-08-02", WF_NUMBER, positions=())]))
    assert result.transactions == []
    assert result.skipped["refund before 2026-07-29"] == 1
    [warning] = result.warnings
    assert WF_NUMBER in warning and "4.99" in warning


def test_whole_foods_refund_with_positions_fails_loudly(tmp_path):
    with pytest.raises(ImporterError, match=f"{WF_NUMBER}.*positions"):
        _parse(_write(tmp_path, _whole_foods(),
                      refunds=[_refund(4.99, "2026-09-12", WF_NUMBER, positions=(1,))]))


def test_refund_with_no_positions_on_a_physical_order_fails_loudly(tmp_path):
    with pytest.raises(ImporterError, match="111-0000000-0000009.*positions"):
        _parse(_write(tmp_path, _order(), refunds=[_refund(4.99, positions=())]))


def test_refund_with_no_positions_for_an_order_missing_from_the_file_is_skipped(tmp_path):
    result = _parse(_write(tmp_path, _order(),
                           refunds=[_refund(4.99, order_number=WF_NUMBER, positions=())]))
    assert _refund_rows(result) == []
    assert result.skipped["refund without item"] == 1
    [warning] = result.warnings
    assert WF_NUMBER in warning and "4.99" in warning


# --- Order-level tax (schema version 2) -----------------------------------------

def test_order_level_tax_is_spread_across_every_shipment_by_net_price(tmp_path):
    # tax 1.00 over 30.00 / 10.00 in two shipments -> 0.75 / 0.25
    order = _multi(41.00, _shipment(_item(1, 30.00), tax=None),
                   _shipment(_item(2, 10.00), tax=None), tax=1.00)
    result, rows = _rows(tmp_path, order)
    assert rows["1"].amount_formula == "=30+0.75"
    assert rows["2"].amount_formula == "=10+0.25"
    assert result.warnings == []


def test_order_level_tax_leftover_cent_goes_to_the_largest_part(tmp_path):
    # $1.00 over three equal Items: 0.33 each, leftover cent to the first largest
    order = _multi(31.00, _shipment(_item(1, 10.00), _item(2, 10.00), tax=None),
                   _shipment(_item(3, 10.00), tax=None), tax=1.00)
    _, rows = _rows(tmp_path, order)
    assert [rows[k].amount_formula for k in "123"] == ["=10+0.34", "=10+0.33", "=10+0.33"]


def test_order_level_tax_weights_are_price_after_promos_without_shipping(tmp_path):
    # net 10 and 5 after a $5 promo on #2 -> tax 0.30 splits 0.20 / 0.10
    order = _multi(19.30, _shipment(_item(1, 10.00), tax=None, shipping=4.00),
                   _shipment(_item(2, 10.00), tax=None), tax=0.30,
                   promos=[{"name": "Save $5", "amount": 5.00, "positions": [2]}])
    _, rows = _rows(tmp_path, order)
    assert rows["1"].amount_formula == "=10+0.2+4"
    assert rows["2"].amount_formula == "=10-5+0.1"


def test_own_tax_wins_and_order_level_tax_remainder_goes_to_the_rest(tmp_path):
    # Order tax 2.00 includes #1's own 0.50; the other 1.50 splits 1.00 / 0.50
    order = _multi(42.00, _shipment(_item(1, 10.00, tax=0.50), _item(2, 20.00), tax=None),
                   _shipment(_item(3, 10.00), tax=None), tax=2.00)
    _, rows = _rows(tmp_path, order)
    assert rows["1"].amount_formula == "=10+0.5"
    assert rows["2"].amount_formula == "=20+1"
    assert rows["3"].amount_formula == "=10+0.5"


def test_shipment_tax_wins_over_order_level_tax(tmp_path):
    # Shipment 1 shows its own 0.40; the Order's 1.00 leaves 0.60 for shipment 2
    order = _multi(21.00, _shipment(_item(1, 10.00), tax=0.40),
                   _shipment(_item(2, 10.00), tax=None), tax=1.00)
    _, rows = _rows(tmp_path, order)
    assert rows["1"].amount_formula == "=10+0.4"
    assert rows["2"].amount_formula == "=10+0.6"


def test_order_level_tax_is_ignored_when_every_shipment_shows_tax(tmp_path):
    order = _multi(20.80, _shipment(_item(1, 10.00), tax=0.40),
                   _shipment(_item(2, 10.00), tax=0.40), tax=0.80)
    result, rows = _rows(tmp_path, order)
    assert rows["1"].amount_formula == "=10+0.4"
    assert rows["2"].amount_formula == "=10+0.4"
    assert result.warnings == []


def test_cancelled_item_takes_no_order_level_tax(tmp_path):
    order = _multi(21.00, _shipment(_item(1, 20.00), tax=None),
                   _shipment(_item(2, 50.00, cancelled=True), tax=None), tax=1.00)
    result, rows = _rows(tmp_path, order)
    assert list(rows) == ["1"]
    assert rows["1"].amount_formula == "=20+1"
    assert result.warnings == []


def test_no_tax_shown_anywhere_means_zero_tax(tmp_path):
    order = _multi(20.00, _shipment(_item(1, 10.00), tax=None),
                   _shipment(_item(2, 10.00), tax=None), tax=None)
    result, rows = _rows(tmp_path, order)
    assert rows["1"].amount_formula == "=10"
    assert rows["2"].amount_formula == "=10"
    assert result.warnings == []


def test_no_tax_shown_anywhere_leaves_the_total_check_to_decide(tmp_path):
    order = _multi(21.65, _shipment(_item(1, 10.00), tax=None),
                   _shipment(_item(2, 10.00), tax=None), tax=None)
    result = _parse(_write(tmp_path, order))
    assert result.transactions == []
    assert result.skipped["total mismatch"] == 2
    assert "21.65" in result.warnings[0] and "20.00" in result.warnings[0]


def test_order_without_a_tax_field_fails_loudly(tmp_path):
    order = _multi(10.83, _shipment(_item(1, 10.00), tax=0.83))
    del order["tax"]
    with pytest.raises(ImporterError, match="111-0000000-0000009: missing 'tax'"):
        _parse(_write(tmp_path, order))


def test_shipment_without_a_tax_field_fails_loudly(tmp_path):
    order = _multi(10.83, _shipment(_item(1, 10.00)), tax=0.83)
    del order["shipments"][0]["tax"]
    with pytest.raises(ImporterError, match="111-0000000-0000009 shipment: missing 'tax'"):
        _parse(_write(tmp_path, order))


@pytest.mark.parametrize("tax", ["1.00", True, 1.005])
def test_bad_order_level_tax_names_the_order(tmp_path, tax):
    order = _multi(11.00, _shipment(_item(1, 10.00), tax=None), tax=tax)
    with pytest.raises(ImporterError, match="111-0000000-0000009.*tax"):
        _parse(_write(tmp_path, order))


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


def test_order_entirely_before_the_cutoff_is_ignored_even_if_totals_disagree(tmp_path):
    order = _multi(99.99, _shipment_on("2026-07-20", _item(1, 10.00, tax=0)))
    result = _parse(_write(tmp_path, order))
    assert result.transactions == []
    assert result.skipped["before 2026-07-29"] == 1
    assert result.skipped["total mismatch"] == 0
    assert result.warnings == []


def _refund(amount, refund_date="2026-08-20", order_number="111-0000000-0000009", positions=(1,)):
    return {"order_number": order_number, "positions": list(positions),
            "amount": amount, "refund_date": refund_date}


def _refund_rows(result):
    return [t for t in result.transactions if t.refunds]


def test_refund_becomes_a_negative_row_on_the_refund_date(tmp_path):
    result = _parse(_write(tmp_path, _order(), refunds=[_refund(10.83)]))
    [refund] = _refund_rows(result)
    assert refund.date == date(2026, 8, 20)
    assert refund.amount == -10.83
    assert refund.amount_formula is None
    assert refund.description == "Refund: Fakebrand Widget"
    assert refund.account == "Amazon Card"
    assert refund.key == "amazon 111-0000000-0000009 #1 refund 2026-08-20 10.83"
    assert refund.refunds == "amazon 111-0000000-0000009 #1"
    assert result.warnings == []


def test_several_partial_refunds_on_one_item_stay_distinct(tmp_path):
    result = _parse(_write(tmp_path, _order(), refunds=[
        _refund(3.00, "2026-08-20"), _refund(3.00, "2026-08-25"), _refund(2.50, "2026-08-25")]))
    assert [t.key for t in _refund_rows(result)] == [
        "amazon 111-0000000-0000009 #1 refund 2026-08-20 3.00",
        "amazon 111-0000000-0000009 #1 refund 2026-08-25 3.00",
        "amazon 111-0000000-0000009 #1 refund 2026-08-25 2.50",
    ]


def test_refund_on_an_item_shipped_before_the_cutoff_is_skipped_with_a_warning(tmp_path):
    order = _multi(10.00, _shipment_on("2026-07-20", _item(1, 10.00, tax=0)))
    result = _parse(_write(tmp_path, order, refunds=[_refund(4.25, "2026-08-02")]))
    assert result.transactions == []
    assert result.skipped["refund before 2026-07-29"] == 1
    [warning] = result.warnings
    assert "111-0000000-0000009" in warning and "4.25" in warning


def test_refund_for_an_order_missing_from_the_file_is_skipped_with_a_warning(tmp_path):
    result = _parse(_write(tmp_path, _order(),
                           refunds=[_refund(5.00, order_number="111-0000000-0000077")]))
    assert _refund_rows(result) == []
    assert result.skipped["refund without item"] == 1
    [warning] = result.warnings
    assert "111-0000000-0000077 #1" in warning and "5.00" in warning


def test_refund_for_an_item_in_an_order_not_ready_still_imports(tmp_path):
    # Item #1 shipped and was returned while #2 is still on its way; the CLI
    # holds the Refund until Item #1's row exists.
    order = _multi(20.00,
                   _shipment_on("2026-08-11", _item(1, 10.00, tax=0)),
                   _shipment_on(None, _item(2, 10.00, tax=0), shipped=False))
    result = _parse(_write(tmp_path, order, refunds=[_refund(10.00)]))
    [refund] = _refund_rows(result)
    assert refund.refunds == "amazon 111-0000000-0000009 #1"


@pytest.mark.parametrize("amount", [0, -1.00, 1.005])
def test_refund_amount_must_be_positive_cents(tmp_path, amount):
    with pytest.raises(ImporterError, match="111-0000000-0000009 #1.*refund"):
        _parse(_write(tmp_path, _order(), refunds=[_refund(amount)]))


def test_order_listed_twice_fails_loudly(tmp_path):
    with pytest.raises(ImporterError, match="111-0000000-0000009.*twice"):
        _parse(_write(tmp_path, _order(), _order()))


UNKNOWN_SHIP_NOTE = " (ship date unknown, Order Date used for cutoff)"


def test_unknown_ship_date_with_order_date_on_the_cutoff_imports_with_a_note(tmp_path):
    order = _multi(10.00, _shipment_on(None, _item(1, 10.00, tax=0)), order_date="2026-07-29")
    for shipment in order["shipments"]:
        shipment["shipped"] = True
    result, rows = _rows(tmp_path, order)
    assert list(rows) == ["1"]
    assert rows["1"].key == "amazon 111-0000000-0000009 #1"
    assert rows["1"].note_suffix == UNKNOWN_SHIP_NOTE
    assert rows["1"].date == date(2026, 7, 29)
    [warning] = result.warnings
    assert "111-0000000-0000009" in warning


def test_unknown_ship_date_with_order_date_before_the_cutoff_skips_the_item(tmp_path):
    order = _multi(10.00, _shipment_on(None, _item(1, 10.00, tax=0)), order_date="2026-07-28")
    order["shipments"][0]["shipped"] = True
    result = _parse(_write(tmp_path, order))
    assert result.transactions == []
    assert result.skipped["unknown ship date"] == 1
    assert result.skipped["before 2026-07-29"] == 0
    [warning] = result.warnings
    assert "111-0000000-0000009" in warning
    assert "#1" in warning and "Item skipped" in warning


def test_unknown_ship_date_skip_names_only_the_items_it_drops(tmp_path):
    order = _multi(30.00,
                   _shipment_on(None, _item(1, 10.00, tax=0), _item(2, 10.00, tax=0)),
                   _shipment_on("2026-08-01", _item(3, 10.00, tax=0)),
                   order_date="2026-07-20")
    order["shipments"][0]["shipped"] = True
    result, rows = _rows(tmp_path, order)
    assert list(rows) == ["3"]
    assert result.skipped["unknown ship date"] == 2
    assert len(result.warnings) == 2
    assert all("Item skipped" in w and "Order skipped" not in w for w in result.warnings)
    assert ["#1" in w for w in result.warnings] == [True, False]
    assert ["#2" in w for w in result.warnings] == [False, True]


def test_known_ship_date_never_gets_the_note(tmp_path):
    _, rows = _rows(tmp_path, _multi(10.00, _shipment_on("2026-08-02", _item(1, 10.00, tax=0))))
    assert rows["1"].note_suffix == ""


def test_only_the_shipment_without_a_ship_date_falls_back(tmp_path):
    order = _multi(20.00,
                   _shipment_on("2026-07-20", _item(1, 10.00, tax=0)),
                   _shipment_on(None, _item(2, 10.00, tax=0)),
                   order_date="2026-08-01")
    order["shipments"][1]["shipped"] = True
    result, rows = _rows(tmp_path, order)
    assert list(rows) == ["2"]
    assert rows["2"].note_suffix == UNKNOWN_SHIP_NOTE
    assert result.skipped["before 2026-07-29"] == 1
    assert len(result.warnings) == 1


def test_refund_on_an_item_with_no_ship_date_uses_the_order_date(tmp_path):
    order = _multi(10.00, _shipment_on(None, _item(1, 10.00, tax=0)), order_date="2026-08-01")
    order["shipments"][0]["shipped"] = True
    result = _parse(_write(tmp_path, order, refunds=[_refund(4.25, "2026-08-20")]))
    [refund] = _refund_rows(result)
    assert refund.amount == -4.25


def test_refund_on_an_item_with_no_ship_date_and_an_old_order_date_is_skipped(tmp_path):
    order = _multi(10.00, _shipment_on(None, _item(1, 10.00, tax=0)), order_date="2026-07-20")
    order["shipments"][0]["shipped"] = True
    result = _parse(_write(tmp_path, order, refunds=[_refund(4.25, "2026-08-20")]))
    assert result.transactions == []
    assert result.skipped["refund before 2026-07-29"] == 1
    assert any("4.25" in w and "111-0000000-0000009" in w for w in result.warnings)


def test_discount_with_unknown_targets_is_spread_as_a_discount_with_a_warning(tmp_path):
    # $3 over net 20 / 10 -> 2 / 1, written in the discount term
    order = _multi(27.00, _shipment(_item(1, 20.00, tax=0), _item(2, 10.00, tax=0)),
                   promos=[{"name": "Coupon", "amount": 3.00, "positions": []}])
    result, rows = _rows(tmp_path, order)
    assert rows["1"].amount_formula == "=20-2"
    assert rows["2"].amount_formula == "=10-1"
    assert result.warnings == [
        "amazon order 111-0000000-0000009: discount of 3.00 has no Items Amazon shows; "
        "spread across every Item"]
    assert not result.skipped


def test_discount_with_unknown_targets_spreads_by_price_after_own_promos(tmp_path):
    # $5 promo on #2 leaves net 10 / 5; the $3 untargeted discount splits 2 / 1 after it
    order = _multi(12.00, _shipment(_item(1, 10.00, tax=0), _item(2, 10.00, tax=0)),
                   promos=[{"name": "Save $5", "amount": 5.00, "positions": [2]},
                           {"name": "Coupon", "amount": 3.00, "positions": []}])
    _, rows = _rows(tmp_path, order)
    assert rows["1"].amount_formula == "=10-2"
    assert rows["2"].amount_formula == "=10-5-1"


def test_discount_with_unknown_targets_sits_beside_a_whole_order_discount(tmp_path):
    order = _multi(25.00, _shipment(_item(1, 20.00, tax=0), _item(2, 10.00, tax=0)),
                   discounts=[{"name": "Order discount", "amount": 2.00}],
                   promos=[{"name": "Coupon", "amount": 3.00, "positions": []}])
    _, rows = _rows(tmp_path, order)
    assert rows["1"].amount_formula == "=20-3.33"
    assert rows["2"].amount_formula == "=10-1.67"


def test_discount_with_unknown_targets_skips_cancelled_items(tmp_path):
    order = _multi(8.00, _shipment(_item(1, 10.00, tax=0), _item(2, 10.00, tax=0, cancelled=True)),
                   promos=[{"name": "Coupon", "amount": 2.00, "positions": []}])
    _, rows = _rows(tmp_path, order)
    assert list(rows) == ["1"]
    assert rows["1"].amount_formula == "=10-2"


def test_promo_whose_listed_items_were_all_cancelled_is_still_ignored(tmp_path):
    order = _multi(10.00, _shipment(_item(1, 10.00, tax=0), _item(2, 10.00, tax=0, cancelled=True)),
                   promos=[{"name": "Save $3", "amount": 3.00, "positions": [2]}])
    result, rows = _rows(tmp_path, order)
    assert rows["1"].amount_formula == "=10"
    assert result.warnings == []


def test_discount_with_unknown_targets_that_breaks_the_total_still_skips_the_order(tmp_path):
    order = _multi(30.00, _shipment(_item(1, 20.00, tax=0), _item(2, 10.00, tax=0)),
                   promos=[{"name": "Coupon", "amount": 3.00, "positions": []}])
    result, rows = _rows(tmp_path, order)
    assert rows == {}
    assert result.skipped["total mismatch"] == 2


def _two_item_order(price_1=30.00, price_2=10.00, ship_2="2026-08-11"):
    return _multi(price_1 + price_2,
                  _shipment_on("2026-08-11", _item(1, price_1, tax=0)),
                  _shipment_on(ship_2, _item(2, price_2, tax=0)))


def test_refund_covering_several_items_splits_by_loaded_cost(tmp_path):
    result = _parse(_write(tmp_path, _two_item_order(),
                           refunds=[_refund(20.00, positions=[1, 2])]))
    first, second = _refund_rows(result)
    assert (first.amount, second.amount) == (-15.00, -5.00)
    assert (first.description, second.description) == ("Refund: Thing 1", "Refund: Thing 2")
    assert (first.refunds, second.refunds) == ("amazon 111-0000000-0000009 #1",
                                               "amazon 111-0000000-0000009 #2")
    assert first.key == "amazon 111-0000000-0000009 #1 refund 2026-08-20 15.00"
    assert second.key == "amazon 111-0000000-0000009 #2 refund 2026-08-20 5.00"
    assert first.date == second.date == date(2026, 8, 20)
    assert result.warnings == []


def test_split_parts_sum_to_the_refund_and_none_has_the_wrong_sign(tmp_path):
    # $0.05 across three equal Items: 2, 2, 1 cents, never a negative part.
    order = _multi(30.00, *(_shipment_on("2026-08-11", _item(n, 10.00, tax=0)) for n in (1, 2, 3)))
    result = _parse(_write(tmp_path, order, refunds=[_refund(0.05, positions=[1, 2, 3])]))
    amounts = [t.amount for t in _refund_rows(result)]
    assert sorted(amounts) == [-0.02, -0.02, -0.01]
    assert round(sum(amounts), 2) == -0.05
    assert all(a < 0 for a in amounts)


def test_split_weights_include_each_items_tax_and_shipping(tmp_path):
    # Loaded Costs 10.00 + 1.00 tax = 11.00 and 10.00 + 4.00 tax = 14.00.
    order = _multi(25.00, _shipment_on("2026-08-11", _item(1, 10.00, tax=1.00), _item(2, 10.00, tax=4.00)))
    result = _parse(_write(tmp_path, order, refunds=[_refund(25.00, positions=[1, 2])]))
    assert [t.amount for t in _refund_rows(result)] == [-11.00, -14.00]


def test_one_position_refund_keeps_its_plain_key(tmp_path):
    result = _parse(_write(tmp_path, _two_item_order(), refunds=[_refund(7.00, positions=[2])]))
    [refund] = _refund_rows(result)
    assert refund.amount == -7.00
    assert refund.key == "amazon 111-0000000-0000009 #2 refund 2026-08-20 7.00"


def test_split_ignores_items_the_refund_does_not_list(tmp_path):
    order = _multi(60.00, *(_shipment_on("2026-08-11", _item(n, 20.00, tax=0)) for n in (1, 2, 3)))
    result = _parse(_write(tmp_path, order, refunds=[_refund(10.00, positions=[1, 3])]))
    assert [(t.refunds[-2:], t.amount) for t in _refund_rows(result)] == [("#1", -5.00), ("#3", -5.00)]


def test_refund_listing_an_item_that_matches_nothing_skips_the_whole_refund(tmp_path):
    result = _parse(_write(tmp_path, _two_item_order(),
                           refunds=[_refund(20.00, positions=[1, 9])]))
    assert _refund_rows(result) == []
    assert result.skipped["refund without item"] == 1
    [warning] = result.warnings
    assert "#9" in warning and "20.00" in warning


def test_refund_listing_an_unshipped_item_skips_the_whole_refund(tmp_path):
    order = _multi(40.00, _shipment_on("2026-08-11", _item(1, 30.00, tax=0)),
                   _shipment_on(None, _item(2, 10.00, tax=0), shipped=False))
    result = _parse(_write(tmp_path, order, refunds=[_refund(20.00, positions=[1, 2])]))
    assert _refund_rows(result) == []
    assert result.skipped["refund without item"] == 1


def test_refund_listing_an_item_before_the_cutoff_skips_the_whole_refund(tmp_path):
    result = _parse(_write(tmp_path, _two_item_order(ship_2="2026-07-20"),
                           refunds=[_refund(20.00, positions=[1, 2])]))
    assert _refund_rows(result) == []
    assert result.skipped["refund before 2026-07-29"] == 1
    [warning] = result.warnings
    assert "20.00" in warning and "2026-07-29" in warning


def test_refund_positions_must_be_a_nonempty_list_of_distinct_whole_numbers(tmp_path):
    for positions in ([], [1, 1], ["1"]):
        with pytest.raises(ImporterError, match="111-0000000-0000009.*positions"):
            _parse(_write(tmp_path, _order(), refunds=[_refund(5.00, positions=positions)]))


def test_the_old_single_position_field_is_rejected(tmp_path):
    old = {"order_number": "111-0000000-0000009", "position": 1,
           "amount": 5.00, "refund_date": "2026-08-20"}
    with pytest.raises(ImporterError, match="111-0000000-0000009.*positions"):
        _parse(_write(tmp_path, _order(), refunds=[old]))


# The scrape prompt's example file is the contract the scraper is shown, so it
# must be a file the importer accepts, and it must show every shape.
PROMPT = Path(__file__).parent.parent / "scrape-amazon-orders.md"
EXAMPLE_HEADING = "### File format (schema version 2)"


def _prompt_example(tmp_path) -> Path:
    text = PROMPT.read_text()
    after = text.split(EXAMPLE_HEADING, 1)[1]
    block = after.split("```json\n", 1)[1].split("\n```", 1)[0]
    f = tmp_path / "amazon-orders-2026-10-01.json"
    f.write_text(block)
    return f


def test_the_scrape_prompt_example_parses_with_the_importer(tmp_path):
    result = _parse(_prompt_example(tmp_path))
    rows = {t.key: t for t in result.transactions}
    assert len(result.transactions) == len(rows) == 10
    assert dict(result.skipped) == {}

    # Physical Order with per-shipment tax, an Item-targeted Promo and a refund covering two Items.
    assert rows["amazon 111-0000000-0000001 #1"].amount_formula.startswith("=2*12.99-3+")
    assert {k for k, t in rows.items()
            if k.startswith("amazon 111-0000000-0000001 #") and not t.refunds} == {
        f"amazon 111-0000000-0000001 #{n}" for n in (1, 2, 3)}
    refunds = [t for t in result.transactions if t.refunds]
    assert sorted(t.refunds for t in refunds) == [
        "amazon 111-0000000-0000001 #2", "amazon 111-0000000-0000001 #3",
        "amazon 111-0000000-0000002"]
    assert sum(t.amount for t in refunds if t.refunds.endswith(("#2", "#3"))) == pytest.approx(-17.50)

    # Order-level tax, a null ship date and a discount with unknown targets.
    assert rows["amazon 111-0000000-0000004 #1"].note_suffix == amazon.UNKNOWN_SHIP_DATE_NOTE
    assert any("discount of 1.48" in w for w in result.warnings)
    assert sum(t.amount for k, t in rows.items()
               if k.startswith("amazon 111-0000000-0000004 #")) == pytest.approx(26.18)

    # Whole Foods Order (one row, formula of the summary lines) and a Digital Order.
    assert rows["amazon 111-0000000-0000002"].description == "Whole Foods"
    assert rows["amazon 111-0000000-0000002"].amount_formula == "=106.99+7-3"
    digital = rows["amazon D01-0000000-0000003"]
    assert (digital.description, digital.date, digital.amount) == (
        "Grocery Subscription", date(2026, 9, 9), 9.99)
    assert all(t.account == "Amazon Card" for t in result.transactions)
