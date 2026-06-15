import re
import pdfplumber
from dataclasses import dataclass
from datetime import date
from pathlib import Path


@dataclass
class Transaction:
    date: date
    description: str
    amount: float
    card_name: str


# Matches lines like: "05/20   WHOLE FOODS MARKET   45.67"
# Negative amounts (payments) are matched but filtered out below.
_TXN_PATTERN = re.compile(
    r"^(\d{2}/\d{2})\s{2,}(.+?)\s{2,}-?(\$?[\d,]+\.\d{2})$",
    re.MULTILINE,
)

_SKIP_KEYWORDS = {"PAYMENT", "CREDIT", "AUTOPAY", "THANK YOU", "BALANCE"}


def _is_payment(description: str) -> bool:
    upper = description.upper()
    return any(kw in upper for kw in _SKIP_KEYWORDS)


def parse_transactions(
    text: str,
    card_name: str,
    year: int,
    billing_start: date | None = None,
) -> list[Transaction]:
    """Extract purchase transactions from PDF text.

    Args:
        text: Raw text extracted from the PDF.
        card_name: Label written to the sheet.
        year: The base year (usually the statement's closing year).
        billing_start: If provided, January dates are assigned year+1 when
                       billing_start is in December (handles Dec→Jan windows).
    """
    results = []
    for match in _TXN_PATTERN.finditer(text):
        raw_date, description, raw_amount = match.groups()
        description = description.strip()
        if _is_payment(description):
            continue
        month, day = map(int, raw_date.split("/"))
        # Handle Dec→Jan year rollover: if billing window starts in Dec and
        # this transaction is in Jan, it belongs to year+1.
        txn_year = year
        if billing_start is not None and billing_start.month == 12 and month == 1:
            txn_year = year + 1
        txn_date = date(txn_year, month, day)
        amount = float(raw_amount.replace(",", "").replace("$", ""))
        results.append(Transaction(date=txn_date, description=description,
                                   amount=amount, card_name=card_name))
    return results


def parse_pdf(
    pdf_path: str | Path,
    card_name: str,
    year: int,
    billing_start: date | None = None,
) -> list[Transaction]:
    """Extract all transactions from a PDF file."""
    all_text = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                all_text.append(text)
    return parse_transactions(
        "\n".join(all_text),
        card_name=card_name,
        year=year,
        billing_start=billing_start,
    )
