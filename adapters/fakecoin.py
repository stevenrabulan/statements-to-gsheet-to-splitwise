from datetime import datetime

from models import Transaction, ParseResult, ImporterError

NAME = "fakecoin"

# columns parse() actually reads — missing any of these is a hard error
_REQUIRED = ("Date", "Amount", "Type", "Status", "Merchant")
# distinctive columns used only for matches() routing (not all are read)
_SIGNATURE = {"Type", "Status", "Merchant", "Card Last Four", "Reward Rate"}
_GOOD_STATUS = {"AUTHORIZED", "SETTLED", "CLEARED"}
_DEAD_STATUS = {"DECLINED", "REVERSED", "CANCELED", "CANCELLED", "FAILED"}


def matches(header: list[str]) -> bool:
    return _SIGNATURE.issubset({h.strip() for h in header})


def _require_columns(rows: list[dict]) -> None:
    if not rows:
        return
    missing = [c for c in _REQUIRED if c not in rows[0]]
    if missing:
        raise ImporterError(f"fakecoin: missing expected column(s): {', '.join(missing)}")


def parse(rows: list[dict], account: str) -> ParseResult:
    if not account:
        raise ImporterError("fakecoin: account label is required")
    _require_columns(rows)
    result = ParseResult()
    for i, row in enumerate(rows, start=2):  # row 1 is the header
        txn_type = (row.get("Type") or "").strip().upper()
        if txn_type != "PURCHASE":
            result.skipped["payment/deposit"] += 1
            continue
        status = (row.get("Status") or "").strip().upper()
        if status in _DEAD_STATUS:
            result.skipped["dead status"] += 1
            continue
        if status not in _GOOD_STATUS:
            result.warnings.append(
                f"row {i}: unknown status {status!r} — imported anyway")

        raw_date = (row.get("Date") or "").strip()
        raw_amount = (row.get("Amount") or "").strip()
        try:
            txn_date = datetime.strptime(raw_date, "%Y-%m-%d").date()
        except ValueError:
            raise ImporterError(f"fakecoin row {i}: unparseable date {raw_date!r}")
        try:
            amount = abs(float(raw_amount.replace(",", "").replace("$", "")))
        except ValueError:
            raise ImporterError(f"fakecoin row {i}: unparseable amount {raw_amount!r}")

        result.transactions.append(Transaction(
            date=txn_date,
            description=(row.get("Merchant") or "").strip(),
            amount=amount,
            account=account,
        ))
    return result
