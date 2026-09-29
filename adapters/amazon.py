"""Amazon Orders adapter: a scraped Order file (JSON) -> one Transaction per Item.

The file holds only what Amazon shows (ADR 0002). Every sum and rounding
happens here, in Decimal, and each row's Amount is written as a formula.
"""
import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from models import AccountConfig, ImporterError, ParseResult, Transaction

NAME = "amazon"
SCHEMA_VERSION = 1

GIFT_CARD_LABEL = "Amazon Gift Card"
POINTS_LABEL = "Points"
_PAYMENT_TYPES = {"card", "gift_card", "points"}

CENT = Decimal("0.01")

# Every Amazon row's Notes carry a stable key (spec, "Deduplication"):
# "amazon <order number> #<position>", plus " refund <date> <amount>" on a Refund.
# Matched as whole words, so "#1" never matches "#10" and an Item key never
# matches its Refund's key.
KEY_PATTERN = re.compile(r"(?<!\S)amazon \S+ #\d+(?: refund \S+ \S+)?(?!\S)")


def item_key(order_number: str, position: int) -> str:
    return f"amazon {order_number} #{position}"


def parse_orders(path: Path, config: AccountConfig,
                 accounts: dict[str, AccountConfig]) -> ParseResult:
    """Parse a scraped Order file. `config` is the Amazon accounts.json entry;
    `accounts` is the full map, used to turn a card's last four into a label."""
    if config is None:
        raise ImporterError(f"{path.name}: amazon: an accounts.json entry is required")
    data = _load(path)
    result = ParseResult()
    for order in _get(data, "orders", list, "file"):
        _parse_order(order, config, accounts, result)
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
    order_date = _date(_get(order, "order_date", str, where), where)
    shipments = _get(order, "shipments", list, where)
    items = [item for shipment in shipments
             for item in _get(shipment, "items", list, where)]

    if not _ready(shipments, where):
        result.skipped["not ready"] += sum(
            1 for item in items if not _cancelled(item, where))
        return

    costs = _loaded_costs(order, shipments, where)
    expected = _money(_get(order, "order_total", (int, Decimal), where), f"{where} order_total")
    calculated = sum((c.loaded for c in costs), Decimal(0))
    if calculated != expected:
        result.skipped["total mismatch"] += len(costs)
        result.warnings.append(
            f"amazon {where}: expected total {expected:.2f} but calculated {calculated:.2f}; "
            f"Order skipped")
        return

    account, warning = _payment_method(_get(order, "payment", list, where),
                                       where, config, accounts)
    if warning:
        result.warnings.append(warning)
    for cost in costs:
        if config.ignore_before is not None and cost.shipped_on < config.ignore_before:
            result.skipped[f"before {config.ignore_before.isoformat()}"] += 1
            continue
        result.transactions.append(_item_row(cost, order_number, order_date, account))


def _ready(shipments, where: str) -> bool:
    """An Order is ready once every non-cancelled Item's shipment has shipped."""
    for shipment in shipments:
        shipped = shipment.get("shipped")
        if not isinstance(shipped, bool):
            raise ImporterError(f"amazon {where}: shipment 'shipped' must be true or false, got {shipped!r}")
        if not shipped and any(not _cancelled(item, where)
                               for item in _get(shipment, "items", list, where)):
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
    shipped_on: date | None = None   # its shipment's ship date; the cutoff compares this
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


def _loaded_costs(order, shipments, where) -> list[_ItemCost]:
    """Loaded Cost for every non-cancelled Item, in the spec's order: Promos,
    then tax, then shipping and whole-Order discounts."""
    groups = []     # [(shipment, [_ItemCost])], so shipment-scope spreads know their Items
    for shipment in shipments:
        costs = [_item_cost(item, where) for item in _get(shipment, "items", list, where)
                 if not _cancelled(item, where)]
        if costs:
            shipped_on = _date(_get(shipment, "ship_date", str, where), where)
            for cost in costs:
                cost.shipped_on = shipped_on
        groups.append((shipment, costs))
    costs = [c for _, group in groups for c in group]

    for promo in _get(order, "promos", list, where):
        positions = _get(promo, "positions", list, where)
        targets = [c for c in costs if c.position in positions]
        if not targets:
            continue    # every targeted Item was cancelled
        amount = _money(_get(promo, "amount", (int, Decimal), where), f"{where} promo")
        for cost, part in zip(targets, _spread(amount, [c.line for c in targets])):
            cost.promo += part

    for shipment, group in groups:
        # Shipment tax already includes any per-Item tax Amazon also shows.
        rest = [c for c in group if c.own_tax is None]
        for cost in group:
            if cost.own_tax is not None:
                cost.tax = cost.own_tax
        tax = _money(_get(shipment, "tax", (int, Decimal), where), f"{where} shipment tax")
        remainder = max(tax - sum((c.tax for c in group), Decimal(0)), Decimal(0))
        for cost, part in zip(rest, _spread(remainder, [c.net for c in rest])):
            cost.tax = part

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

    for discount in _get(order, "discounts", list, where):
        amount = _money(_get(discount, "amount", (int, Decimal), where), f"{where} discount")
        for cost, part in zip(costs, _spread(amount, [c.net for c in costs])):
            cost.discount += part
    return costs


def _cancelled(item, where: str) -> bool:
    flag = item.get("cancelled") if isinstance(item, dict) else None
    if not isinstance(flag, bool):
        raise ImporterError(f"amazon {where}: item 'cancelled' must be true or false, got {flag!r}")
    return flag


def _item_cost(item, order_where) -> _ItemCost:
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
    return _ItemCost(position, short_name, quantity, unit_price, quantity * unit_price, own_tax)


def _spread(total: Decimal, weights: list[Decimal]) -> list[Decimal]:
    """Split `total` across `weights` in cents. Parts sum exactly to `total`;
    the leftover goes to the largest weight (the first one on a tie)."""
    if not weights or not total:
        return [Decimal(0)] * len(weights)
    if not sum(weights):
        weights = [Decimal(1)] * len(weights)
    whole = sum(weights)
    parts = [(total * w / whole).quantize(CENT, rounding=ROUND_HALF_UP) for w in weights]
    parts[weights.index(max(weights))] += total - sum(parts)
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
