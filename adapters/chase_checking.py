from datetime import datetime

from models import Transaction, ParseResult, ImporterError

NAME = "chase-checking"

# columns parse() actually reads — missing any of these is a hard error
_REQUIRED = ("Details", "Posting Date", "Description", "Amount", "Type")
# distinctive columns for matches() routing (no overlap with chase-credit/discover/fakecoin)
_SIGNATURE = {"Details", "Posting Date", "Balance", "Check or Slip #"}

_TRANSFER_TYPES = {"ACCT_XFER"}
_CARD_PAYMENT_TYPES = {"LOAN_PMT"}
# description markers (whitespace-collapsed, upper) identifying a credit-card payment
_CARD_PAYMENT_MARKERS = ("CARD PAYMENT", "CC PAYMENT", "E-PAYMENT", "FAKECARD")
# crypto purchases from checking (excluded per the user's rule)
_CRYPTO_MARKERS = ("FAKECOIN INC", "FAKECOIN.COM")


def matches(header: list[str]) -> bool:
    return _SIGNATURE.issubset({h.strip() for h in header})


def _require(rows: list[dict]) -> None:
    if rows:
        missing = [c for c in _REQUIRED if c not in rows[0]]
        if missing:
            raise ImporterError(f"chase-checking: missing column(s): {', '.join(missing)}")


def parse(rows: list[dict], account: str) -> ParseResult:
    if not account:
        raise ImporterError("chase-checking: account label is required")
    _require(rows)
    result = ParseResult()
    for i, row in enumerate(rows, start=2):
        details = (row.get("Details") or "").strip().upper()
        txn_type = (row.get("Type") or "").strip().upper()
        desc = (row.get("Description") or "").strip()
        norm = " ".join(desc.upper().split())

        if details != "DEBIT":                       # CREDIT / DSLIP = money in
            result.skipped["deposit/credit"] += 1
            continue
        if txn_type in _TRANSFER_TYPES:
            result.skipped["transfer"] += 1
            continue
        if txn_type in _CARD_PAYMENT_TYPES or any(m in norm for m in _CARD_PAYMENT_MARKERS):
            result.skipped["card payment"] += 1
            continue
        if txn_type == "ATM" or "WITHDRAWAL" in norm:
            result.skipped["atm/cash"] += 1
            continue
        if any(m in norm for m in _CRYPTO_MARKERS):
            result.skipped["crypto"] += 1
            continue

        raw_date = (row.get("Posting Date") or "").strip()
        raw_amount = (row.get("Amount") or "").strip()
        try:
            txn_date = datetime.strptime(raw_date, "%m/%d/%Y").date()
        except ValueError:
            raise ImporterError(f"chase-checking row {i}: bad date {raw_date!r}")
        try:
            amount = abs(float(raw_amount.replace(",", "").replace("$", "")))
        except ValueError:
            raise ImporterError(f"chase-checking row {i}: bad amount {raw_amount!r}")
        # checking descriptions are heavily space-padded; collapse for a clean sheet value
        result.transactions.append(Transaction(
            date=txn_date, description=" ".join(desc.split()), amount=amount, account=account))
    return result
