from collections import Counter
from dataclasses import dataclass, field
from datetime import date


class ImporterError(Exception):
    """Raised for any user-facing import failure (fail loud)."""


@dataclass
class Transaction:
    date: date
    description: str
    amount: float            # positive spend, negative refund; rounded to cents at write
    account: str             # column G label (card or bank account name)
    source_file: str = ""    # import file basename — used for the column-K note
    # Amazon Item rows only; card rows leave these unset.
    amount_formula: str | None = None      # column B formula, e.g. "=2*12.99+1.81"
    key: str | None = None                 # stable dedup key, written to column K
    send_to_splitwise: bool | None = None  # column E; None = the default (ticked)
    for_who: str | None = None             # column H; None = left for the sheet to fill


@dataclass(frozen=True)
class AccountConfig:
    name: str                        # column G label (card or bank account name)
    ignore_before: date | None = None  # drop transactions dated before this day


@dataclass
class ParseResult:
    transactions: list[Transaction] = field(default_factory=list)
    skipped: Counter = field(default_factory=Counter)   # reason -> count (dropped rows)
    warnings: list[str] = field(default_factory=list)   # imported-but-flagged rows
