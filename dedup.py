from collections import Counter
from datetime import date, datetime, timedelta

from adapters.amazon import KEY_PATTERN as AMAZON_KEY_PATTERN
from models import ImporterError, Transaction

# Google Sheets stores dates as days since this epoch (shared with Excel).
SHEETS_EPOCH = date(1899, 12, 30)

# Plausible serial range: ~1900-01-01 through ~2173. Anything outside is not a date.
_MIN_SERIAL, _MAX_SERIAL = 1, 100_000

# Accepted text date layouts, most-specific first. Only used for cells that are
# stored as text rather than real dates.
_DATE_FORMATS = ("%m/%d/%Y", "%Y/%m/%d", "%Y-%m-%d", "%m/%d/%y")

# Below this many candidate rows, a zero-parse result is unremarkable (small
# fixtures, empty sheet). At or above it, zero parses means dedup is broken.
_SANITY_MIN_ROWS = 10


def _coerce_date(value) -> date:
    """Sheet cell -> date. Accepts a serial number or a text date."""
    if isinstance(value, bool) or value is None:
        raise ValueError(f"not a date: {value!r}")
    if isinstance(value, (int, float)):
        serial = int(value)
        if not _MIN_SERIAL <= serial <= _MAX_SERIAL:
            raise ValueError(f"date serial out of range: {value!r}")
        return SHEETS_EPOCH + timedelta(days=serial)
    text = str(value).strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"unrecognized date: {value!r}")


def _coerce_amount(value) -> float:
    """Sheet cell -> float. Accepts a number or currency text like "$1,234.56"."""
    if isinstance(value, bool) or value is None:
        raise ValueError(f"not an amount: {value!r}")
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).replace("$", "").replace(",", "").strip()
    if text.startswith("(") and text.endswith(")"):     # (5.00) = -5.00
        text = "-" + text[1:-1].strip()
    return float(text)


def _amazon_key(key: str) -> tuple:
    return ("amazon", key)


def _key(txn_date, amount, description, account):
    return (
        txn_date,
        round(float(amount), 2),
        " ".join(str(description).upper().split()),
        str(account).strip().upper(),
    )


def existing_keys_from_rows(rows: list[list]) -> Counter:
    """Build a multiset of keys from raw sheet rows (cols A,B,C,G, plus any
    Amazon key in col K).

    Rows that don't parse (headers, blanks, formula rows) are ignored. Raises if
    a sheet full of candidate rows yields nothing — a silent zero here would let
    every transaction through as "new" and duplicate the whole import.
    """
    counter: Counter = Counter()
    candidates = 0
    for row in rows:
        if not row or str(row[0]).strip() == "":
            continue
        candidates += 1
        if len(row) > 10:
            for key in AMAZON_KEY_PATTERN.findall(str(row[10])):
                counter[_amazon_key(key)] += 1
        try:
            d = _coerce_date(row[0])
            amt = _coerce_amount(row[1])
            desc = row[2]
            account = row[6]
        except (IndexError, ValueError, TypeError, AttributeError):
            continue
        counter[_key(d, amt, desc, account)] += 1

    if candidates >= _SANITY_MIN_ROWS and not counter:
        raise ImporterError(
            f"dedup: none of the {candidates} populated sheet rows could be parsed as "
            f"(date, amount) — refusing to import, since every row would look new and "
            f"the sheet would be duplicated. Check that column A holds dates and "
            f"column B amounts."
        )
    return counter


def dedup(incoming: list[Transaction], existing: Counter) -> list[Transaction]:
    """Return incoming transactions not already present in `existing`.

    Consumes one count per match so genuine repeat charges are preserved.
    Does NOT count its own output — re-importing the same export adds nothing.
    Amazon rows match on their stable key alone, so a re-scrape whose amount
    moved by a cent is still recognized.
    """
    remaining = Counter(existing)
    kept = []
    for txn in incoming:
        k = (_amazon_key(txn.key) if txn.key
             else _key(txn.date, txn.amount, txn.description, txn.account))
        if remaining[k] > 0:
            remaining[k] -= 1
        else:
            kept.append(txn)
    return kept
