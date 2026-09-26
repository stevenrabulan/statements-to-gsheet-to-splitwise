from datetime import datetime

from models import Transaction, ParseResult, ImporterError

NAME = "chase-credit"

# columns parse() actually reads — missing any of these is a hard error
_REQUIRED = ("Transaction Date", "Description", "Type", "Amount")
# distinctive columns used only for matches() routing (not all are read)
_SIGNATURE = {"Transaction Date", "Post Date", "Category", "Type", "Memo"}
# non-Sale/Return Type -> skipped reason
_DROP_TYPES = {"PAYMENT": "payment/deposit",
               "FEE": "credit/refund", "ADJUSTMENT": "credit/refund"}


def matches(header: list[str]) -> bool:
    return _SIGNATURE.issubset({h.strip() for h in header})


def _require(rows: list[dict]) -> None:
    if rows:
        missing = [c for c in _REQUIRED if c not in rows[0]]
        if missing:
            raise ImporterError(f"chase-credit: missing column(s): {', '.join(missing)}")


def parse(rows: list[dict], account: str) -> ParseResult:
    if not account:
        raise ImporterError("chase-credit: account label is required")
    _require(rows)
    result = ParseResult()
    for i, row in enumerate(rows, start=2):
        txn_type = (row.get("Type") or "").strip().upper()
        if txn_type not in ("SALE", "RETURN"):
            result.skipped[_DROP_TYPES.get(txn_type, "credit/refund")] += 1
            continue
        raw_date = (row.get("Transaction Date") or "").strip()
        raw_amount = (row.get("Amount") or "").strip()
        try:
            txn_date = datetime.strptime(raw_date, "%m/%d/%Y").date()
        except ValueError:
            raise ImporterError(f"chase-credit row {i}: bad date {raw_date!r}")
        try:
            amount = abs(float(raw_amount.replace(",", "").replace("$", "")))
            if txn_type == "RETURN":
                amount = -amount                 # refund reduces spend
        except ValueError:
            raise ImporterError(f"chase-credit row {i}: bad amount {raw_amount!r}")
        result.transactions.append(Transaction(
            date=txn_date, description=(row.get("Description") or "").strip(),
            amount=amount, account=account))
    return result
