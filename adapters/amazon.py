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

# Every Order says what it is. Only physical Orders are imported so far; the
# other kinds are counted as skipped under their CONTEXT.md names.
_PHYSICAL = "physical"
_NOT_IMPORTED_YET = {"whole_foods": "Whole Foods Order", "digital": "Digital Order"}
_KINDS = {_PHYSICAL, *_NOT_IMPORTED_YET}

GIFT_CARD_LABEL = "Amazon Gift Card"
POINTS_LABEL = "Points"
_PAYMENT_TYPES = {"card", "gift_card", "points"}

CENT = Decimal("0.01")

# Every Amazon row's Notes carry a stable key (spec, "Deduplication"):
# "amazon <order number> #<position>", plus " refund <date> <amount>" on a Refund.
# Matched as whole words, so "#1" never matches "#10" and an Item key never
# matches its Refund's key.
_ITEM_KEY = r"amazon \S+ #\d+"
KEY_PATTERN = re.compile(rf"(?<!\S){_ITEM_KEY}(?: refund \S+ \S+)?(?!\S)")
# Fullmatched against a KEY_PATTERN match: an Item's key, not a Refund's.
ITEM_KEY_PATTERN = re.compile(_ITEM_KEY)

# Added after the key in Notes when the ship date was unknown (spec addendum, decision 3).
UNKNOWN_SHIP_DATE_NOTE = " (ship date unknown, Order Date used for cutoff)"
UNKNOWN_SHIP_DATE = "unknown ship date"


def item_key(order_number: str, position: int) -> str:
    return f"amazon {order_number} #{position}"


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
    if kind in _NOT_IMPORTED_YET:
        result.skipped[f"{_NOT_IMPORTED_YET[kind]} (not imported yet)"] += 1
        return
    order_date = _date(_get(order, "order_date", str, where), where)
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
    expected = _money(_get(order, "order_total", (int, Decimal), where), f"{where} order_total")
    calculated = sum((c.loaded for c in costs), Decimal(0))
    if calculated != expected:
        result.skipped["total mismatch"] += len(costs)
        result.warnings.append(
            f"amazon {where}: expected total {expected:.2f} but calculated {calculated:.2f}; "
            f"Order skipped")
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


def _count_before_cutoff(cost: "_ItemCost", cutoff: date, where: str, result: ParseResult) -> None:
    """Count an Item dropped by the cutoff. One that only fell back to the Order
    Date is named in a warning, once per Order, since nothing else says why."""
    if cost.ship_date_known:
        result.skipped[f"before {cutoff.isoformat()}"] += 1
        return
    result.skipped[UNKNOWN_SHIP_DATE] += 1
    warning = (f"amazon {where}: ship date unknown and the Order Date is before the "
               f"{cutoff.isoformat()} cutoff; Order skipped")
    if warning not in result.warnings:
        result.warnings.append(warning)


def _parse_refund(refund, orders: dict, config, accounts, result: ParseResult) -> None:
    """A Refund becomes a plain negative row. Its classification is copied from
    the Item's sheet row later, by the CLI, which can see the sheet."""
    order_number = _get(refund, "order_number", str, "refund")
    position = _get(refund, "position", int, f"refund on order {order_number}")
    where = f"order {order_number} #{position}"
    amount = _money(_get(refund, "amount", (int, Decimal), f"{where} refund"),
                    f"{where} refund amount")
    if amount <= 0:
        raise ImporterError(f"amazon {where}: refund amount must be positive, got {amount}")
    refund_date = _date(_get(refund, "refund_date", str, f"{where} refund"), f"{where} refund")
    what = f"Refund of {amount:.2f} on {refund_date.isoformat()}"

    order = orders.get(order_number)
    if order is not None and order["kind"] in _NOT_IMPORTED_YET:
        label = _NOT_IMPORTED_YET[order["kind"]]
        result.skipped[f"refund on {label} (not imported yet)"] += 1
        result.warnings.append(f"amazon {where}: {what} is on a {label}, which is not "
                               f"imported yet; Refund skipped")
        return
    found = _shipped_item(order, position, where) if order else None
    if found is None:
        result.skipped["refund without item"] += 1
        result.warnings.append(f"amazon {where}: {what} matches no shipped Item in this file; "
                               f"Refund skipped, enter it by hand")
        return
    short_name, shipped_on, known = found
    cutoff = config.ignore_before
    if cutoff is not None and shipped_on < cutoff:
        # The Item is a Charge row from before Item rows existed.
        result.skipped[f"refund before {cutoff.isoformat()}"] += 1
        how = (f"shipped {shipped_on.isoformat()}" if known
               else f"with no ship date, ordered {shipped_on.isoformat()}")
        result.warnings.append(f"amazon {where}: {what} is for an Item {how}, before the "
                               f"{cutoff.isoformat()} cutoff; Refund skipped, enter it by hand")
        return

    account, warning = _payment_method(_get(order, "payment", list, f"order {order_number}"),
                                       f"order {order_number}", config, accounts)
    if warning and warning not in result.warnings:
        result.warnings.append(warning)
    item = item_key(order_number, position)
    result.transactions.append(Transaction(
        date=refund_date,
        description=f"Refund: {short_name}",
        amount=-float(amount),
        account=account,
        key=refund_key(item, refund_date, amount),
        refunds=item,
    ))


def _shipped_item(order, position: int, where: str) -> tuple[str, date, bool] | None:
    """(short name, cutoff date, whether it is a real ship date) of the Order's
    shipped, non-cancelled Item at `position`, or None when there is no such Item.
    With no ship date the Order Date is the cutoff date."""
    for shipment in _get(order, "shipments", list, where):
        if shipment.get("shipped") is not True:
            continue
        for item in _live_items(shipment, where):
            if item.get("position") == position:
                shipped_on, known = _ship_date(shipment, order, where)
                return (_get(item, "short_name", str, where).strip(), shipped_on, known)
    return None


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
    then tax, then shipping and whole-Order discounts. A Promo with no known
    targets is an Adjustment (CONTEXT.md): it joins the discounts, and `notices`
    gets a warning for it."""
    groups = []     # [(shipment, [_ItemCost])], so shipment-scope spreads know their Items
    for shipment in shipments:
        live = _live_items(shipment, where)
        shipped_on, known = _ship_date(shipment, order, where) if live else (None, True)
        costs = [_item_cost(item, where, shipped_on, known) for item in live]
        groups.append((shipment, costs))
    costs = [c for _, group in groups for c in group]

    untargeted = []     # amounts of coupons whose Items Amazon doesn't show
    for promo in _get(order, "promos", list, where):
        positions = _get(promo, "positions", list, where)
        amount = _money(_get(promo, "amount", (int, Decimal), where), f"{where} promo")
        if not positions:
            if costs:
                untargeted.append(amount)
                notices.append(f"amazon {where}: coupon of {amount:.2f} has no Items Amazon "
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
