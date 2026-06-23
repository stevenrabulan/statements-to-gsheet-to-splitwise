from datetime import datetime

from models import Transaction, ParseResult, ImporterError

NAME = "fakemart_credit"

_REQUIRED = ("Date", "Amount", "Type", "Merchant")
_SIGNATURE = {"Date", "Amount", "Type", "Merchant", "Category", "Method"}
_KEEP_TYPES = {"transaction", "refund"}


def matches(header: list[str]) -> bool:
    return _SIGNATURE == {h.strip() for h in header}


def _require(rows: list[dict]) -> None:
    if rows:
        missing = [c for c in _REQUIRED if c not in rows[0]]
        if missing:
            raise ImporterError(f"fakemart_credit: missing column(s): {', '.join(missing)}")


def parse(rows: list[dict], account: str) -> ParseResult:
    if not account:
        raise ImporterError("fakemart_credit: account label is required")
    _require(rows)
    result = ParseResult()
    for i, row in enumerate(rows, start=2):
        txn_type = (row.get("Type") or "").strip().lower()
        if txn_type not in _KEEP_TYPES:
            result.skipped["payment/other"] += 1
            continue
        raw_date = (row.get("Date") or "").strip()
        raw_amount = (row.get("Amount") or "").strip()
        # date format: "2026/06/22, 15:13:12"
        try:
            txn_date = datetime.strptime(raw_date, "%Y/%m/%d, %H:%M:%S").date()
        except ValueError:
            raise ImporterError(f"fakemart_credit row {i}: bad date {raw_date!r}")
        try:
            amount = float(raw_amount.replace(",", "").replace("$", ""))
        except ValueError:
            raise ImporterError(f"fakemart_credit row {i}: bad amount {raw_amount!r}")
        result.transactions.append(Transaction(
            date=txn_date,
            description=(row.get("Merchant") or "").strip(),
            amount=amount,
            account=account,
        ))
    return result
