from collections import Counter
from datetime import datetime

from models import Transaction


def _key(txn_date, amount, description, account):
    return (
        txn_date,
        round(float(amount), 2),
        " ".join(str(description).upper().split()),
        str(account).strip().upper(),
    )


def existing_keys_from_rows(rows: list[list]) -> Counter:
    """Build a multiset of keys from raw sheet rows (cols A,B,C,G).

    Rows that don't parse (headers, blanks, formula rows) are ignored.
    """
    counter: Counter = Counter()
    for row in rows:
        try:
            d = datetime.strptime(str(row[0]).strip(), "%m/%d/%Y").date()
            amt = float(str(row[1]).replace("$", "").replace(",", "").strip())
            desc = row[2]
            account = row[6]
        except (IndexError, ValueError, TypeError, AttributeError):
            continue
        counter[_key(d, amt, desc, account)] += 1
    return counter


def dedup(incoming: list[Transaction], existing: Counter) -> list[Transaction]:
    """Return incoming transactions not already present in `existing`.

    Consumes one count per match so genuine repeat charges are preserved.
    Does NOT count its own output — re-importing the same export adds nothing.
    """
    remaining = Counter(existing)
    kept = []
    for txn in incoming:
        k = _key(txn.date, txn.amount, txn.description, txn.account)
        if remaining[k] > 0:
            remaining[k] -= 1
        else:
            kept.append(txn)
    return kept
