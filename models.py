from collections import Counter
from dataclasses import dataclass, field
from datetime import date


class ImporterError(Exception):
    """Raised for any user-facing import failure (fail loud)."""


@dataclass
class Transaction:
    date: date
    description: str
    amount: float            # positive spend, rounded to cents at write
    account: str             # column G label (card or bank account name)
    source_file: str = ""    # import file basename — used for the column-K note


@dataclass(frozen=True)
class AccountConfig:
    name: str                        # column G label (card or bank account name)
    ignore_before: date | None = None  # drop transactions dated before this day


@dataclass
class ParseResult:
    transactions: list[Transaction] = field(default_factory=list)
    skipped: Counter = field(default_factory=Counter)   # reason -> count (dropped rows)
    warnings: list[str] = field(default_factory=list)   # imported-but-flagged rows
