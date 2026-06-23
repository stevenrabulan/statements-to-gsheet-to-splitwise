from datetime import datetime

from models import Transaction, ParseResult, ImporterError

NAME = "discover"

# columns parse() actually reads — missing any of these is a hard error
_REQUIRED = ("Trans. Date", "Description", "Amount", "Category")
# distinctive columns used only for matches() routing (exact set distinguishes from chase-credit)
_SIGNATURE = {"Trans. Date", "Post Date", "Description", "Amount", "Category"}


def matches(header: list[str]) -> bool:
    return _SIGNATURE == {h.strip() for h in header}


def _require(rows: list[dict]) -> None:
    if rows:
        missing = [c for c in _REQUIRED if c not in rows[0]]
        if missing:
            raise ImporterError(f"discover: missing column(s): {', '.join(missing)}")


def parse(rows: list[dict], account: str) -> ParseResult:
    if not account:
        raise ImporterError("discover: account label is required")
    _require(rows)
    result = ParseResult()
    for i, row in enumerate(rows, start=2):
        if (row.get("Category") or "").strip() == "Payments and Credits":
            result.skipped["credit/refund"] += 1
            continue
        raw_date = (row.get("Trans. Date") or "").strip()
        raw_amount = (row.get("Amount") or "").strip()
        try:
            txn_date = datetime.strptime(raw_date, "%m/%d/%Y").date()
        except ValueError:
            raise ImporterError(f"discover row {i}: bad date {raw_date!r}")
        try:
            amount = float(raw_amount.replace(",", "").replace("$", ""))
        except ValueError:
            raise ImporterError(f"discover row {i}: bad amount {raw_amount!r}")
        if amount <= 0:                          # refund/credit not flagged by category
            result.skipped["credit/refund"] += 1
            continue
        result.transactions.append(Transaction(
            date=txn_date, description=(row.get("Description") or "").strip(),
            amount=amount, account=account))
    return result
