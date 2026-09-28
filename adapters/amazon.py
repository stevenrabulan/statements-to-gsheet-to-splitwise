"""Amazon Orders adapter: a scraped Order file (JSON) -> one Transaction per Item.

The file holds only what Amazon shows (ADR 0002). Every sum and rounding
happens here, in Decimal, and each row's Amount is written as a formula.
"""
import json
import re
from datetime import date, datetime
from decimal import Decimal
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

    if _needs_allocation(order, shipments, items, where):
        result.skipped["needs cost allocation"] += len(items)
        result.warnings.append(
            f"amazon {where}: has promos, shipping, discounts, or shipment-only tax, "
            f"which this importer can't allocate yet; skipped")
        return

    account, warning = _payment_method(_get(order, "payment", list, where),
                                       where, config, accounts)
    if warning:
        result.warnings.append(warning)
    for item in items:
        result.transactions.append(_item_row(item, order_number, order_date, account, where))


def _needs_allocation(order, shipments, items, where) -> bool:
    """True when some part of the Order's cost isn't on a single Item."""
    if _get(order, "promos", list, where) or _get(order, "discounts", list, where):
        return True
    if _money(_get(order, "shipping", (int, Decimal), where), f"{where} shipping"):
        return True
    for shipment in shipments:
        if "shipping" not in shipment:      # null = no separate shipment shipping
            raise ImporterError(f"amazon {where} shipment: missing 'shipping'")
        if shipment["shipping"] is not None and _money(shipment["shipping"], f"{where} shipment shipping"):
            return True
    return any(item.get("tax") is None for item in items)


def _item_row(item, order_number: str, order_date: date, account: str,
              order_where: str) -> Transaction:
    position = _get(item, "position", int, order_where)
    where = f"{order_where} #{position}"
    short_name = _get(item, "short_name", str, where).strip()
    if not short_name:
        raise ImporterError(f"amazon {where}: short_name must not be empty")
    quantity = _get(item, "quantity", int, where)
    if quantity < 1:
        raise ImporterError(f"amazon {where}: quantity must be at least 1, got {quantity}")
    unit_price = _money(_get(item, "unit_price", (int, Decimal), where), f"{where} unit_price")
    tax = _money(_get(item, "tax", (int, Decimal), where), f"{where} tax")

    loaded_cost = quantity * unit_price + tax
    formula = _dollars(unit_price) if quantity == 1 else f"{quantity}*{_dollars(unit_price)}"
    if tax:
        formula += f"+{_dollars(tax)}"
    return Transaction(
        date=order_date,
        description=short_name if quantity == 1 else f"{quantity}× {short_name}",
        amount=float(loaded_cost),
        account=account,
        amount_formula=f"={formula}",
        key=item_key(order_number, position),
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
