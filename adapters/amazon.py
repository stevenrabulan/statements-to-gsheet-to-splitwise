"""Amazon Orders adapter: a scraped Order file (JSON) -> one Transaction per Item.

The file holds only what Amazon shows (ADR 0002). Every sum and rounding
happens here, in Decimal, and each row's Amount is written as a formula.
"""
import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import ROUND_FLOOR, Decimal
from pathlib import Path

from models import AccountConfig, ImporterError, ParseResult, Transaction

NAME = "amazon"
SCHEMA_VERSION = 2

# Every Order says what it is.
_PHYSICAL = "physical"
_WHOLE_FOODS = "whole_foods"
_DIGITAL = "digital"
_KINDS = {_PHYSICAL, _WHOLE_FOODS, _DIGITAL}
WHOLE_FOODS_LABEL = "Whole Foods"

GIFT_CARD_LABEL = "Amazon Gift Card"
POINTS_LABEL = "Points"
_PAYMENT_TYPES = {"card", "gift_card", "points"}

CENT = Decimal("0.01")

# Every Amazon row's Notes carry a stable key (spec, "Deduplication"):
# "amazon <order number> #<position>" for an Item, "amazon <order number>" for a
# Whole Foods or Digital Order, plus " refund <date> <amount>" on a Refund (the amount of
# that Item's part when one Refund covers several Items).
# Matched as whole words, longest form first, so "#1" never matches "#10" and an
# Order key never matches an Item key or a Refund key that starts with it.
_ROW_KEY = r"amazon \S+(?: #\d+)?"
KEY_PATTERN = re.compile(rf"(?<!\S){_ROW_KEY}(?: refund \S+ \S+)?(?!\S)")
# Fullmatched against a KEY_PATTERN match: the key of a row that Refunds point
# at (an Item or a Whole Foods Order), not a Refund's own key.
ROW_KEY_PATTERN = re.compile(_ROW_KEY)

# Added after the key in Notes when the ship date was unknown (spec addendum, decision 3).
UNKNOWN_SHIP_DATE_NOTE = " (ship date unknown, Order Date used for cutoff)"
UNKNOWN_SHIP_DATE = "unknown ship date"


def item_key(order_number: str, position: int) -> str:
    return f"amazon {order_number} #{position}"


def order_key(order_number: str) -> str:
    return f"amazon {order_number}"


def refund_key(item: str, refund_date: date, amount: Decimal) -> str:
    """Date and amount keep several partial refunds on one Item distinct."""
    return f"{item} refund {refund_date.isoformat()} {amount:.2f}"


def parse_orders(path: Path, config: AccountConfig,
                 accounts: dict[str, AccountConfig]) -> ParseResult:
    """Parse a scraped Order file. `config` is the Amazon accounts.json entry;
    `accounts` is the full map, used to turn a card's last four into a label."""
    if config is None:
        raise ImporterError(f"{path.name}: amazon: an accounts.json entry is required")
    data = _load(path)
    result = ParseResult()
    orders = {}
    for order in _get(data, "orders", list, "file"):
        _parse_order(order, config, accounts, result)
        if order["order_number"] in orders:
            raise ImporterError(f"amazon order {order['order_number']}: listed twice in the file")
        orders[order["order_number"]] = order
    for refund in _get(data, "refunds", list, "file"):
        _parse_refund(refund, orders, config, accounts, result)
    return result


def _load(path: Path) -> dict:
    try:
        data = json.loads(Path(path).read_text(), parse_float=Decimal)
    except json.JSONDecodeError as exc:
        raise ImporterError(f"{Path(path).name}: not valid JSON ({exc})")
    if not isinstance(data, dict):
        raise ImporterError(f"{Path(path).name}: expected a JSON object at the top level")
    version = data.get("schema_version")
    if version != SCHEMA_VERSION:
        raise ImporterError(
            f"{Path(path).name}: schema_version is {version!r}, expected {SCHEMA_VERSION}. "
            f"The scrape prompt and the importer disagree on the file format."
        )
    return data


def _parse_order(order, config, accounts, result: ParseResult) -> None:
    if not isinstance(order, dict):
        raise ImporterError(f"amazon: each order must be an object, got {order!r}")
    order_number = _get(order, "order_number", str, "order")
    where = f"order {order_number}"
    kind = order.get("kind")
    if not isinstance(kind, str) or kind not in _KINDS:
        raise ImporterError(
            f"amazon {where}: 'kind' must be one of {sorted(_KINDS)}, got {kind!r}")
    if kind == _DIGITAL:
        _parse_digital(order, order_number, config, accounts, result)
        return
    order_date = _date(_get(order, "order_date", str, where), where)
    if kind == _WHOLE_FOODS:
        _parse_whole_foods(order, order_number, order_date, config, accounts, result)
        return
    shipments = _get(order, "shipments", list, where)

    if not _ready(shipments, where):
        result.skipped["not ready"] += sum(len(_live_items(sh, where)) for sh in shipments)
        return

    notices = []    # warnings that belong to the Order only if it is imported
    costs = _loaded_costs(order, shipments, where, notices)
    cutoff = config.ignore_before
    if cutoff is not None and all(c.shipped_on < cutoff for c in costs):
        # Recorded as Charge rows already; its totals are not our concern.
        for cost in costs:
            _count_before_cutoff(cost, cutoff, where, result)
        return
    mismatch = _total_mismatch(order, costs, where)
    if mismatch:
        result.skipped["total mismatch"] += len(costs)
        result.warnings.append(f"amazon {where}: {mismatch}; Order skipped")
        return

    result.warnings += notices
    account, warning = _payment_method(_get(order, "payment", list, where),
                                       where, config, accounts)
    if warning:
        result.warnings.append(warning)
    for cost in costs:
        if cutoff is not None and cost.shipped_on < cutoff:
            _count_before_cutoff(cost, cutoff, where, result)
            continue
        if not cost.ship_date_known:
            result.warnings.append(
                f"amazon {where}: ship date unknown for #{cost.position}; Order Date "
                f"{order_date.isoformat()} used for the cutoff")
        result.transactions.append(_item_row(cost, order_number, order_date, account))


def _parse_whole_foods(order, order_number: str, order_date: date, config, accounts,
                       result: ParseResult) -> None:
    """A Whole Foods Order is one row for the whole Order, tip included, with no
    Items (decision 7). The cutoff compares the Order Date."""
    where = f"order {order_number}"
    delivered = order.get("delivered")
    if not isinstance(delivered, bool):
        raise ImporterError(f"amazon {where}: 'delivered' must be true or false, got {delivered!r}")
    if not delivered:
        result.skipped["not ready"] += 1
        return
    cutoff = config.ignore_before
    if cutoff is not None and order_date < cutoff:
        result.skipped[f"before {cutoff.isoformat()}"] += 1
        return

    additions = _lines(order, "additions", where)
    if not additions:
        raise ImporterError(f"amazon {where}: 'additions' must list at least one line")
    discounts = _lines(order, "discounts", where)
    expected = _money(_get(order, "order_total", (int, Decimal), where), f"{where} order_total")
    calculated = sum(additions, Decimal(0)) - sum(discounts, Decimal(0))
    if calculated != expected:
        result.skipped["total mismatch"] += 1
        result.warnings.append(
            f"amazon {where}: expected total {expected:.2f} but calculated {calculated:.2f}; "
            f"Order skipped")
        return

    account, warning = _payment_method(_get(order, "payment", list, where),
                                       where, config, accounts)
    if warning:
        result.warnings.append(warning)
    formula = "+".join(_dollars(a) for a in additions) + "".join(f"-{_dollars(a)}" for a in discounts)
    result.transactions.append(Transaction(
        date=order_date,
        description=WHOLE_FOODS_LABEL,
        amount=float(calculated),
        account=account,
        amount_formula=f"={formula}",
        key=order_key(order_number),
    ))


def _parse_digital(order, order_number: str, config, accounts, result: ParseResult) -> None:
    """A Digital Order has nothing to ship, so it is one row, dated when it was
    charged (decision 9). Its Amount is the amount Amazon shows, a plain number."""
    where = f"order {order_number}"
    charge_date = _date(_get(order, "charge_date", str, where), where)
    cutoff = config.ignore_before
    if cutoff is not None and charge_date < cutoff:
        result.skipped[f"before {cutoff.isoformat()}"] += 1
        return
    short_name = _get(order, "short_name", str, where).strip()
    if not short_name:
        raise ImporterError(f"amazon {where}: short_name must not be empty")
    total = _money(_get(order, "order_total", (int, Decimal), where), f"{where} order_total")
    account, warning = _payment_method(_get(order, "payment", list, where),
                                       where, config, accounts)
    if warning:
        result.warnings.append(warning)
    result.transactions.append(Transaction(
        date=charge_date,
        description=short_name,
        amount=float(total),
        account=account,
        key=order_key(order_number),
    ))


def _total_mismatch(order, costs: list["_ItemCost"], where: str) -> str | None:
    """How the Loaded Costs fail the total check (ADR 0002), or None when they
    sum exactly to the Order Total."""
    expected = _money(_get(order, "order_total", (int, Decimal), where), f"{where} order_total")
    calculated = sum((c.loaded for c in costs), Decimal(0))
    if calculated == expected:
        return None
    return f"expected total {expected:.2f} but calculated {calculated:.2f}"


def _lines(order, field: str, where: str) -> list[Decimal]:
    """The dollar amounts of the summary lines Amazon shows under `field`."""
    return [_money(_get(line, "amount", (int, Decimal), f"{where} {field}"), f"{where} {field}")
            for line in _get(order, field, list, where)]


def _count_before_cutoff(cost: "_ItemCost", cutoff: date, where: str, result: ParseResult) -> None:
    """Count an Item dropped by the cutoff. One that only fell back to the Order
    Date is named in a warning, since nothing else says why."""
    if cost.ship_date_known:
        result.skipped[f"before {cutoff.isoformat()}"] += 1
        return
    result.skipped[UNKNOWN_SHIP_DATE] += 1
    result.warnings.append(
        f"amazon {where}: ship date unknown for #{cost.position}; Order Date "
        f"{cost.shipped_on.isoformat()} is before the {cutoff.isoformat()} cutoff; Item skipped")


def _parse_refund(refund, orders: dict, config, accounts, result: ParseResult) -> None:
    """A Refund becomes plain negative rows, one per Item it covers. Each row's
    classification is copied from its Item's sheet row later, by the CLI, which
    can see the sheet."""
    order_number = _get(refund, "order_number", str, "refund")
    order = orders.get(order_number)
    positions = _get(refund, "positions", list, f"refund on order {order_number}")
    order_where = f"order {order_number}"
    if order is not None and order["kind"] == _WHOLE_FOODS:
        _parse_whole_foods_refund(refund, order, positions, config, accounts, result)
        return
    if order is not None and order["kind"] == _DIGITAL:
        amount, refund_date = _refund_amount_and_date(refund, order_where)
        result.skipped["refund on Digital Order"] += 1
        result.warnings.append(
            f"amazon {order_where}: Refund of {amount:.2f} on {refund_date.isoformat()} is on "
            f"a Digital Order, which has no Items to refund; Refund skipped, enter it by hand")
        return
    if order is None and not positions:
        # Only a Whole Foods Order has no positions, but this one is not in the file.
        amount, refund_date = _refund_amount_and_date(refund, order_where)
        result.skipped["refund without item"] += 1
        result.warnings.append(f"amazon {order_where}: Refund of {amount:.2f} on "
                               f"{refund_date.isoformat()} matches no Order in this file; "
                               f"Refund skipped, enter it by hand")
        return
    if (not positions or len(set(positions)) != len(positions)
            or any(isinstance(p, bool) or not isinstance(p, int) for p in positions)):
        raise ImporterError(f"amazon {order_where}: refund 'positions' must list at least one "
                            f"distinct whole number, got {positions!r}")
    where = f"{order_where} " + ", ".join(f"#{p}" for p in positions)
    amount, refund_date = _refund_amount_and_date(refund, where)
    if amount <= 0:
        raise ImporterError(f"amazon {where}: refund amount must be positive, got {amount}")
    what = f"Refund of {amount:.2f} on {refund_date.isoformat()}"

    found = _shipped_items(order, positions, where) if order else None
    if found is None:
        result.skipped["refund without item"] += 1
        result.warnings.append(f"amazon {where}: {what} matches no shipped Item in this file; "
                               f"Refund skipped, enter it by hand")
        return
    cutoff = config.ignore_before
    for short_name, shipped_on, known in found:
        if cutoff is not None and shipped_on < cutoff:
            # The Item is a Charge row from before Item rows existed.
            result.skipped[f"refund before {cutoff.isoformat()}"] += 1
            how = (f"shipped {shipped_on.isoformat()}" if known
                   else f"with no ship date, ordered {shipped_on.isoformat()}")
            result.warnings.append(f"amazon {where}: {what} is for an Item {how}, before the "
                                   f"{cutoff.isoformat()} cutoff; Refund skipped, enter it by hand")
            return

    parts, mismatch = _refund_parts(order, positions, amount, order_where)
    if mismatch:
        result.skipped["refund on total mismatch"] += 1
        result.warnings.append(f"amazon {where}: {what} cannot be split between its Items: "
                               f"the Order fails the total check ({mismatch}); "
                               f"Refund skipped, enter it by hand")
        return
    account, warning = _payment_method(_get(order, "payment", list, order_where),
                                       order_where, config, accounts)
    if warning and warning not in result.warnings:
        result.warnings.append(warning)
    for position, (short_name, _, _), part in zip(positions, found, parts):
        if not part:
            continue    # a share too small to be a cent is not a row
        item = item_key(order_number, position)
        result.transactions.append(Transaction(
            date=refund_date,
            description=f"Refund: {short_name}",
            amount=-float(part),
            account=account,
            key=refund_key(item, refund_date, part),
            refunds=item,
        ))


def _parse_whole_foods_refund(refund, order, positions: list, config, accounts,
                              result: ParseResult) -> None:
    """A Refund on a Whole Foods Order is one negative row against the Order row
    (decision 8). Like an Item Refund it is imported whether or not the Order
    is delivered; the CLI copies the Order row's classification."""
    order_number = order["order_number"]
    where = f"order {order_number}"
    if positions:
        raise ImporterError(f"amazon {where}: a Whole Foods Order has no Items, so its "
                            f"refund 'positions' must be [], got {positions!r}")
    amount, refund_date = _refund_amount_and_date(refund, where)
    if amount <= 0:
        raise ImporterError(f"amazon {where}: refund amount must be positive, got {amount}")
    cutoff = config.ignore_before
    order_date = _date(_get(order, "order_date", str, where), where)
    if cutoff is not None and order_date < cutoff:
        # The Order is a Charge row from before Order rows existed.
        result.skipped[f"refund before {cutoff.isoformat()}"] += 1
        result.warnings.append(
            f"amazon {where}: Refund of {amount:.2f} on {refund_date.isoformat()} is for an "
            f"Order dated {order_date.isoformat()}, before the {cutoff.isoformat()} cutoff; "
            f"Refund skipped, enter it by hand")
        return
    account, warning = _payment_method(_get(order, "payment", list, where),
                                       where, config, accounts)
    if warning and warning not in result.warnings:
        result.warnings.append(warning)
    row = order_key(order_number)
    result.transactions.append(Transaction(
        date=refund_date,
        description=f"Refund: {WHOLE_FOODS_LABEL}",
        amount=-float(amount),
        account=account,
        key=refund_key(row, refund_date, amount),
        refunds=row,
    ))


def _refund_amount_and_date(refund, where: str) -> tuple[Decimal, date]:
    amount = _money(_get(refund, "amount", (int, Decimal), f"{where} refund"),
                    f"{where} refund amount")
    return amount, _date(_get(refund, "refund_date", str, f"{where} refund"), f"{where} refund")


def _refund_parts(order, positions: list[int], amount: Decimal,
                  where: str) -> tuple[list[Decimal], str | None]:
    """Split a Refund across its Items in proportion to their Loaded Costs, so
    each part follows its own Item. The parts sum exactly to `amount`. Returns
    (parts, None), or ([], how the total check failed): Loaded Costs that fail
    it are never used (ADR 0002). One Item needs no split, so no check."""
    if len(positions) == 1:
        return [amount], None
    # The Order's own parse reports these notices; here they would only repeat.
    costs = _loaded_costs(order, _get(order, "shipments", list, where), where, notices=[])
    mismatch = _total_mismatch(order, costs, where)
    if mismatch:
        return [], mismatch
    cost_of = {c.position: c.loaded for c in costs}
    return _spread(amount, [cost_of[p] for p in positions]), None


def _shipped_items(order, positions: list[int], where: str) -> list[tuple[str, date, bool]] | None:
    """(short name, cutoff date, whether it is a real ship date) for each of
    `positions`, in that order, or None when any of them is not a shipped,
    non-cancelled Item of the Order. With no ship date the Order Date is the
    cutoff date."""
    by_position = {}
    for shipment in _get(order, "shipments", list, where):
        if shipment.get("shipped") is not True:
            continue
        for item in _live_items(shipment, where):
            shipped_on, known = _ship_date(shipment, order, where)
            by_position[item.get("position")] = (
                _get(item, "short_name", str, where).strip(), shipped_on, known)
    if any(p not in by_position for p in positions):
        return None
    return [by_position[p] for p in positions]


def _ship_date(shipment, order, where: str) -> tuple[date, bool]:
    """(date the cutoff compares, whether it is the real ship date). A shipped
    shipment with no ship date stands in the Order Date."""
    if shipment.get("ship_date") is None:
        return _date(_get(order, "order_date", str, where), where), False
    return _date(_get(shipment, "ship_date", str, where), where), True


def _live_items(shipment, where: str) -> list:
    """The shipment's Items that were not cancelled."""
    return [item for item in _get(shipment, "items", list, where)
            if not _cancelled(item, where)]


def _ready(shipments, where: str) -> bool:
    """An Order is ready once every non-cancelled Item's shipment has shipped."""
    for shipment in shipments:
        shipped = shipment.get("shipped")
        if not isinstance(shipped, bool):
            raise ImporterError(f"amazon {where}: shipment 'shipped' must be true or false, got {shipped!r}")
        if not shipped and _live_items(shipment, where):
            return False
    return True


@dataclass
class _ItemCost:
    position: int
    short_name: str
    quantity: int
    unit_price: Decimal
    line: Decimal
    own_tax: Decimal | None      # Amazon's per-Item tax, when shown
    shipped_on: date             # its shipment's ship date (else the Order Date); the cutoff compares this
    ship_date_known: bool = True
    promo: Decimal = Decimal(0)
    tax: Decimal = Decimal(0)
    shipping: Decimal = Decimal(0)
    discount: Decimal = Decimal(0)

    @property
    def net(self) -> Decimal:
        return self.line - self.promo

    @property
    def loaded(self) -> Decimal:
        return self.net + self.tax + self.shipping - self.discount


def _loaded_costs(order, shipments, where, notices: list[str]) -> list[_ItemCost]:
    """Loaded Cost for every non-cancelled Item, in the spec's order: Promos,
    then tax, then shipping and whole-Order discounts. A discount whose targets
    Amazon doesn't show is an Adjustment, not a Promo (CONTEXT.md): it joins the
    discounts, and `notices` gets a warning for it."""
    groups = []     # [(shipment, [_ItemCost])], so shipment-scope spreads know their Items
    for shipment in shipments:
        live = _live_items(shipment, where)
        shipped_on, known = _ship_date(shipment, order, where) if live else (None, True)
        costs = [_item_cost(item, where, shipped_on, known) for item in live]
        groups.append((shipment, costs))
    costs = [c for _, group in groups for c in group]

    untargeted = []     # amounts of discounts whose Items Amazon doesn't show
    for promo in _get(order, "promos", list, where):
        positions = _get(promo, "positions", list, where)
        amount = _money(_get(promo, "amount", (int, Decimal), where), f"{where} promo")
        if not positions:
            if costs:
                untargeted.append(amount)
                notices.append(f"amazon {where}: discount of {amount:.2f} has no Items Amazon "
                               f"shows; spread across every Item")
            continue
        targets = [c for c in costs if c.position in positions]
        if not targets:
            continue    # every targeted Item was cancelled
        for cost, part in zip(targets, _spread(amount, [c.line for c in targets])):
            cost.promo += part

    # Tax at the smallest scope Amazon shows: the Item's own, then its shipment's,
    # then the Order's. A wider figure already includes the narrower ones.
    untaxed = []    # Items whose tax Amazon shows only for the whole Order, if at all
    for shipment, group in groups:
        rest = [c for c in group if c.own_tax is None]
        for cost in group:
            if cost.own_tax is not None:
                cost.tax = cost.own_tax
        tax = _shown_tax(shipment, f"{where} shipment")
        if tax is None:
            untaxed += rest
        else:
            _spread_rest_of_tax(tax, group, rest)
    tax = _shown_tax(order, where)
    if tax is not None:
        _spread_rest_of_tax(tax, costs, untaxed)

    # Shipping at the smallest scope Amazon shows: per shipment when given, plus
    # whatever is left at Order scope.
    for shipment, group in groups:
        if shipment.get("shipping") is not None:
            amount = _money(shipment["shipping"], f"{where} shipment shipping")
            for cost, part in zip(group, _spread(amount, [c.net for c in group])):
                cost.shipping += part
    shipping = _money(_get(order, "shipping", (int, Decimal), where), f"{where} shipping")
    for cost, part in zip(costs, _spread(shipping, [c.net for c in costs])):
        cost.shipping += part

    discounts = [_money(_get(d, "amount", (int, Decimal), where), f"{where} discount")
                 for d in _get(order, "discounts", list, where)]
    for amount in discounts + untargeted:
        for cost, part in zip(costs, _spread(amount, [c.net for c in costs])):
            cost.discount += part
    return costs


def _shown_tax(obj, where: str) -> Decimal | None:
    """The tax Amazon shows at this scope, or None when it shows none there.
    The scraper must still write the field, as null."""
    if "tax" not in obj:
        raise ImporterError(f"amazon {where}: missing 'tax' (null when Amazon shows none)")
    return None if obj["tax"] is None else _money(obj["tax"], f"{where} tax")


def _spread_rest_of_tax(tax: Decimal, covered: list[_ItemCost], rest: list[_ItemCost]) -> None:
    """`tax` is Amazon's figure for all of `covered`. What the tax already on
    those Items leaves of it is spread across `rest` by price after Promos."""
    remainder = max(tax - sum((c.tax for c in covered), Decimal(0)), Decimal(0))
    for cost, part in zip(rest, _spread(remainder, [c.net for c in rest])):
        cost.tax = part


def _cancelled(item, where: str) -> bool:
    flag = item.get("cancelled") if isinstance(item, dict) else None
    if not isinstance(flag, bool):
        raise ImporterError(f"amazon {where}: item 'cancelled' must be true or false, got {flag!r}")
    return flag


def _item_cost(item, order_where, shipped_on: date, ship_date_known: bool) -> _ItemCost:
    position = _get(item, "position", int, order_where)
    where = f"{order_where} #{position}"
    short_name = _get(item, "short_name", str, where).strip()
    if not short_name:
        raise ImporterError(f"amazon {where}: short_name must not be empty")
    quantity = _get(item, "quantity", int, where)
    if quantity < 1:
        raise ImporterError(f"amazon {where}: quantity must be at least 1, got {quantity}")
    unit_price = _money(_get(item, "unit_price", (int, Decimal), where), f"{where} unit_price")
    own_tax = (None if item.get("tax") is None
               else _money(item["tax"], f"{where} tax"))
    return _ItemCost(position, short_name, quantity, unit_price, quantity * unit_price,
                     own_tax, shipped_on, ship_date_known)


def _spread(total: Decimal, weights: list[Decimal]) -> list[Decimal]:
    """Split `total` across `weights` in cents. Parts sum exactly to `total`.
    Each part is rounded down, then the leftover cents go one each to the parts
    that lost the most (on a tie, the larger weight, then the earlier one)."""
    if not weights or not total:
        return [Decimal(0)] * len(weights)
    if not sum(weights):
        weights = [Decimal(1)] * len(weights)
    whole = sum(weights)
    exact = [total * w / whole for w in weights]
    parts = [share.quantize(CENT, rounding=ROUND_FLOOR) for share in exact]
    leftover = int((total - sum(parts)) / CENT)
    by_loss = sorted(range(len(parts)),
                     key=lambda i: (parts[i] - exact[i], -weights[i], i))
    for i in by_loss[:leftover]:
        parts[i] += CENT
    return parts


def _item_row(cost: _ItemCost, order_number: str, order_date: date, account: str) -> Transaction:
    formula = _dollars(cost.unit_price)
    if cost.quantity != 1:
        formula = f"{cost.quantity}*{formula}"
    for sign, amount in (("-", cost.promo), ("+", cost.tax),
                         ("+", cost.shipping), ("-", cost.discount)):
        if amount:
            formula += f"{sign}{_dollars(amount)}"
    return Transaction(
        date=order_date,
        description=(cost.short_name if cost.quantity == 1
                     else f"{cost.quantity}× {cost.short_name}"),
        amount=float(cost.loaded),
        account=account,
        amount_formula=f"={formula}",
        key=item_key(order_number, cost.position),
        note_suffix="" if cost.ship_date_known else UNKNOWN_SHIP_DATE_NOTE,
    )


def _payment_method(payment: list, where: str, config: AccountConfig,
                    accounts: dict[str, AccountConfig]) -> tuple[str, str | None]:
    """Return (Payment Method label, warning or None). How an Order was paid
    only labels the row; it never changes Loaded Cost."""
    if not payment:
        raise ImporterError(f"amazon {where}: payment must list at least one method")
    types = []
    for method in payment:
        kind = _get(method, "type", str, f"{where} payment")
        if kind not in _PAYMENT_TYPES:
            raise ImporterError(
                f"amazon {where}: unknown payment type {kind!r}, expected one of "
                f"{sorted(_PAYMENT_TYPES)}")
        types.append(kind)

    cards = [m for m in payment if m["type"] == "card"]
    if cards:
        last_four = _get(cards[0], "last_four", str, f"{where} payment")
        if not (len(last_four) == 4 and last_four.isdigit()):
            raise ImporterError(f"amazon {where}: card last_four must be 4 digits, got {last_four!r}")
        names = sorted({c.name for k, c in accounts.items() if last_four in k})
        if len(names) == 1:
            return names[0], None
        found = "no accounts.json key" if not names else f"several accounts ({names})"
        return config.name, (f"amazon {where}: card ending {last_four} matches {found}; "
                             f"Payment Method set to {config.name!r}")
    if set(types) == {"gift_card"}:
        return GIFT_CARD_LABEL, None
    if set(types) == {"points"}:
        return POINTS_LABEL, None
    return config.name, (f"amazon {where}: paid by {' + '.join(types)} with no card; "
                         f"Payment Method set to {config.name!r}")


def _get(obj, key: str, kind, where: str):
    if not isinstance(obj, dict):
        raise ImporterError(f"amazon {where}: expected an object, got {obj!r}")
    if key not in obj or obj[key] is None:
        raise ImporterError(f"amazon {where}: missing {key!r}")
    value = obj[key]
    if isinstance(value, bool) or not isinstance(value, kind):
        raise ImporterError(f"amazon {where}: {key!r} has the wrong type: {value!r}")
    return value


def _money(value, where: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, Decimal)):
        raise ImporterError(f"amazon {where}: expected a dollar amount, got {value!r}")
    amount = Decimal(value)
    if amount != amount.quantize(CENT):
        raise ImporterError(f"amazon {where}: {value} is not a whole number of cents")
    return amount


def _dollars(amount: Decimal) -> str:
    """12.90 -> "12.9", 3.00 -> "3": the shortest exact form for the formula."""
    return f"{amount:.2f}".rstrip("0").rstrip(".")


def _date(raw: str, where: str) -> date:
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError:
        raise ImporterError(f"amazon {where}: bad date {raw!r}, expected YYYY-MM-DD")
