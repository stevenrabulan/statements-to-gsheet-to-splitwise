# PDF Transactions → Google Sheets Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Parse credit card statement PDFs, filter transactions from the 16th of last month through the 15th of this month, and append one row per transaction to the Google Sheet that feeds Splitwise.

**Architecture:** A Python CLI script accepts one or more PDF paths, extracts transactions using pdfplumber, filters by the billing window, then appends each transaction as a row to the sheet via the Google Sheets API. Sheet columns match the existing `log-amazon-transactions.md` convention: A=date, B=amount, C=description, E=checkbox, G=card name, K=notes.

**Tech Stack:** Python 3.11+, pdfplumber, google-auth, google-api-python-client

---

## File structure

```
split-transactions/
├── main.py                   # CLI entry point — accepts PDF path(s), runs pipeline
├── pdf_parser.py             # Extracts raw transactions from a PDF statement
├── date_filter.py            # Computes billing window, filters transactions
├── sheets_writer.py          # Appends rows to Google Sheet
├── requirements.txt
├── .gitignore                # credentials.json, token.json, *.pdf
└── credentials.json          # (gitignored) OAuth2 Desktop app credentials
```

---

## Prerequisites (do before Task 1)

1. Go to https://console.cloud.google.com → New project → Enable **Google Sheets API**.
2. Create credentials: APIs & Services → Credentials → Create → OAuth 2.0 Client ID → Desktop app → Download as `credentials.json` into the project root.
3. Have at least one credit card statement PDF on hand for manual testing.

---

## Task 1: Project setup

**Files:**
- Create: `requirements.txt`
- Create: `.gitignore`

- [ ] **Step 1: Write `requirements.txt`**

```
pdfplumber==0.11.0
google-auth==2.29.0
google-auth-oauthlib==1.2.0
google-api-python-client==2.127.0
```

- [ ] **Step 2: Write `.gitignore`**

```
credentials.json
token.json
*.pdf
__pycache__/
*.pyc
.env
```

- [ ] **Step 3: Install dependencies**

```bash
pip install -r requirements.txt --break-system-packages
```

Expected: packages install without errors.

- [ ] **Step 4: Commit**

```bash
git add requirements.txt .gitignore
git commit -m "chore: project setup"
```

---

## Task 2: Date filter module

**Files:**
- Create: `date_filter.py`
- Create: `tests/test_date_filter.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_date_filter.py
from datetime import date
from date_filter import billing_window, in_window

def test_billing_window_mid_month():
    # Running on June 10 → window is May 16 – June 15
    start, end = billing_window(today=date(2026, 6, 10))
    assert start == date(2026, 5, 16)
    assert end == date(2026, 6, 15)

def test_billing_window_before_16th():
    # Running on June 1 → still May 16 – June 15
    start, end = billing_window(today=date(2026, 6, 1))
    assert start == date(2026, 5, 16)
    assert end == date(2026, 6, 15)

def test_billing_window_on_16th():
    # Running on June 16 → window is June 16 – July 15
    start, end = billing_window(today=date(2026, 6, 16))
    assert start == date(2026, 6, 16)
    assert end == date(2026, 7, 15)

def test_billing_window_january():
    # Running on Jan 5 → window is Dec 16 – Jan 15
    start, end = billing_window(today=date(2026, 1, 5))
    assert start == date(2025, 12, 16)
    assert end == date(2026, 1, 15)

def test_in_window_inclusive():
    start, end = date(2026, 5, 16), date(2026, 6, 15)
    assert in_window(date(2026, 5, 16), start, end) is True
    assert in_window(date(2026, 6, 15), start, end) is True
    assert in_window(date(2026, 5, 15), start, end) is False
    assert in_window(date(2026, 6, 16), start, end) is False
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_date_filter.py -v
```

Expected: `ModuleNotFoundError: No module named 'date_filter'`

- [ ] **Step 3: Implement `date_filter.py`**

```python
# date_filter.py
from datetime import date
from dateutil.relativedelta import relativedelta


def billing_window(today: date | None = None) -> tuple[date, date]:
    """Return (start, end) of the current billing period.

    The window is the 16th of last month through the 15th of this month,
    unless today is on or after the 16th, in which case the window shifts
    forward by one month.
    """
    if today is None:
        today = date.today()

    if today.day >= 16:
        start = today.replace(day=16)
        end = (today + relativedelta(months=1)).replace(day=15)
    else:
        start = (today - relativedelta(months=1)).replace(day=16)
        end = today.replace(day=15)

    return start, end


def in_window(txn_date: date, start: date, end: date) -> bool:
    return start <= txn_date <= end
```

- [ ] **Step 4: Install python-dateutil (add to requirements.txt too)**

```bash
pip install python-dateutil --break-system-packages
```

Add to `requirements.txt`:
```
python-dateutil==2.9.0
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
python -m pytest tests/test_date_filter.py -v
```

Expected: 5 passed.

- [ ] **Step 6: Commit**

```bash
git add date_filter.py tests/test_date_filter.py requirements.txt
git commit -m "feat: billing window date filter"
```

---

## Task 3: PDF parser module

> **Note on PDF formats:** Credit card PDFs vary by issuer. This task uses Chase Sapphire as the reference format (lines like `05/20 MERCHANT NAME $123.45`). If your PDF uses a different format, follow the "Adapt the regex" sub-steps at the end of this task.

**Files:**
- Create: `pdf_parser.py`
- Create: `tests/test_pdf_parser.py`
- Create: `tests/fixtures/sample_statement.txt` (synthetic fixture — not a real PDF)

- [ ] **Step 1: Inspect your actual PDF**

```bash
python3 -c "
import pdfplumber, sys
with pdfplumber.open(sys.argv[1]) as pdf:
    for i, page in enumerate(pdf.pages[:3]):
        print(f'=== PAGE {i+1} ===')
        print(page.extract_text())
" path/to/your-statement.pdf
```

Study the output. Find a transaction line and note:
- date format (MM/DD vs MM/DD/YYYY)
- whether the amount has a `$` sign
- whether debits and credits are on the same line or separate columns
- the section header that marks where transactions begin (e.g. "ACCOUNT ACTIVITY", "Transactions")

You will use these observations to adapt the regex in Step 3.

- [ ] **Step 2: Write failing tests**

```python
# tests/test_pdf_parser.py
from pdf_parser import parse_transactions, Transaction
from datetime import date

SAMPLE_TEXT = """
ACCOUNT ACTIVITY

Date        Description                     Amount
05/20       WHOLE FOODS MARKET              45.67
05/22       NETFLIX.COM                     15.99
05/23       PAYMENT THANK YOU              -500.00
06/01       AMAZON PRIME                    14.99
"""

def test_parse_returns_transactions():
    txns = parse_transactions(SAMPLE_TEXT, card_name="Chase Sapphire", year=2026)
    assert len(txns) == 3  # payment excluded, 3 purchases

def test_transaction_fields():
    txns = parse_transactions(SAMPLE_TEXT, card_name="Chase Sapphire", year=2026)
    t = txns[0]
    assert t.date == date(2026, 5, 20)
    assert t.description == "WHOLE FOODS MARKET"
    assert t.amount == 45.67
    assert t.card_name == "Chase Sapphire"

def test_excludes_payments():
    txns = parse_transactions(SAMPLE_TEXT, card_name="Chase Sapphire", year=2026)
    descriptions = [t.description for t in txns]
    assert "PAYMENT THANK YOU" not in descriptions

def test_parse_empty_text():
    txns = parse_transactions("", card_name="Chase Sapphire", year=2026)
    assert txns == []
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
python -m pytest tests/test_pdf_parser.py -v
```

Expected: `ModuleNotFoundError: No module named 'pdf_parser'`

- [ ] **Step 4: Implement `pdf_parser.py`**

```python
# pdf_parser.py
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
# Adjust this pattern after inspecting your PDF in Step 1.
_TXN_PATTERN = re.compile(
    r"^(\d{2}/\d{2})\s{2,}(.+?)\s{2,}\$?([\d,]+\.\d{2})$",
    re.MULTILINE,
)

# Keywords in descriptions that indicate payments/credits — skip these rows.
_SKIP_KEYWORDS = {"PAYMENT", "CREDIT", "AUTOPAY", "THANK YOU", "BALANCE"}


def _is_payment(description: str) -> bool:
    upper = description.upper()
    return any(kw in upper for kw in _SKIP_KEYWORDS)


def parse_transactions(text: str, card_name: str, year: int) -> list[Transaction]:
    """Extract purchase transactions from PDF text.

    Args:
        text: Raw text extracted from the PDF.
        card_name: Label written to the sheet (e.g. "Chase Sapphire").
        year: The year to attach to MM/DD dates found in the statement.
              Use the statement's closing year; handle Dec→Jan wraparound manually.

    Returns:
        List of Transaction objects, payments excluded.
    """
    results = []
    for match in _TXN_PATTERN.finditer(text):
        raw_date, description, raw_amount = match.groups()
        description = description.strip()
        if _is_payment(description):
            continue
        month, day = map(int, raw_date.split("/"))
        txn_date = date(year, month, day)
        amount = float(raw_amount.replace(",", ""))
        results.append(Transaction(date=txn_date, description=description,
                                   amount=amount, card_name=card_name))
    return results


def parse_pdf(pdf_path: str | Path, card_name: str, year: int) -> list[Transaction]:
    """Extract all transactions from a PDF file."""
    all_text = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                all_text.append(text)
    return parse_transactions("\n".join(all_text), card_name=card_name, year=year)
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
python -m pytest tests/test_pdf_parser.py -v
```

Expected: 4 passed.

- [ ] **Step 6: Adapt the regex to your actual PDF (if needed)**

If the output from Step 1 shows a different format, update `_TXN_PATTERN` in `pdf_parser.py`. Common variations:

| Format seen in PDF | Regex change |
|---|---|
| `05/20/2026 MERCHANT 45.67` | Change `\d{2}/\d{2}` to `\d{2}/\d{2}/\d{4}` and parse year from match |
| Amount in separate column with no spaces | Use `pdfplumber`'s `extract_table()` instead of `extract_text()` — see note below |
| Negative amounts for purchases, positive for payments | Invert `_is_payment` logic |

**If `extract_table()` is needed:** Replace `parse_pdf` with:
```python
def parse_pdf(pdf_path, card_name, year):
    results = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables():
                for row in table:
                    # row is a list of cell strings; inspect and adapt indices
                    if row and len(row) >= 3:
                        raw_date, description, raw_amount = row[0], row[1], row[-1]
                        # ... same parsing logic as above
    return results
```

- [ ] **Step 7: Commit**

```bash
git add pdf_parser.py tests/test_pdf_parser.py
git commit -m "feat: PDF transaction parser"
```

---

## Task 4: Google Sheets writer

**Files:**
- Create: `sheets_writer.py`
- Create: `tests/test_sheets_writer.py`

The target spreadsheet:
- ID: `YOUR_SPREADSHEET_ID`
- Tab gid: `0` (the writer will resolve the tab name at runtime via the API)

Row layout (columns A–K, 11 values, 0-indexed):

| Index | Column | Value |
|---|---|---|
| 0 | A | Transaction date (`MM/DD/YYYY`) |
| 1 | B | Amount (number) |
| 2 | C | Description |
| 3 | D | _(empty)_ |
| 4 | E | `TRUE` (checkbox) |
| 5 | F | _(empty)_ |
| 6 | G | Card name |
| 7–9 | H–J | _(empty)_ |
| 10 | K | `"Automated by Claude"` |

- [ ] **Step 1: Write failing tests**

```python
# tests/test_sheets_writer.py
from unittest.mock import MagicMock, patch
from datetime import date
from pdf_parser import Transaction
from sheets_writer import build_row, get_sheet_name

def test_build_row():
    txn = Transaction(
        date=date(2026, 5, 20),
        description="WHOLE FOODS MARKET",
        amount=45.67,
        card_name="Chase Sapphire",
    )
    row = build_row(txn)
    assert row[0] == "05/20/2026"
    assert row[1] == 45.67
    assert row[2] == "WHOLE FOODS MARKET"
    assert row[3] == ""
    assert row[4] is True
    assert row[5] == ""
    assert row[6] == "Chase Sapphire"
    assert row[7] == ""
    assert row[8] == ""
    assert row[9] == ""
    assert row[10] == "Automated by Claude"
    assert len(row) == 11

def test_build_row_date_format():
    txn = Transaction(date=date(2026, 1, 5), description="X", amount=1.0, card_name="Y")
    row = build_row(txn)
    assert row[0] == "01/05/2026"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_sheets_writer.py -v
```

Expected: `ModuleNotFoundError: No module named 'sheets_writer'`

- [ ] **Step 3: Implement `sheets_writer.py`**

```python
# sheets_writer.py
import os
from datetime import date
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from pdf_parser import Transaction

SPREADSHEET_ID = "YOUR_SPREADSHEET_ID"
SHEET_GID = 0
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
CREDENTIALS_FILE = Path(__file__).parent / "credentials.json"
TOKEN_FILE = Path(__file__).parent / "token.json"


def build_row(txn: Transaction) -> list:
    """Convert a Transaction to an 11-element list matching the sheet layout."""
    return [
        txn.date.strftime("%m/%d/%Y"),  # A: date
        txn.amount,                      # B: amount
        txn.description,                 # C: description
        "",                              # D: empty
        True,                            # E: checkbox
        "",                              # F: empty
        txn.card_name,                   # G: card name
        "",                              # H: empty
        "",                              # I: empty
        "",                              # J: empty
        "Automated by Claude",           # K: notes
    ]


def _get_credentials() -> Credentials:
    creds = None
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                str(CREDENTIALS_FILE), SCOPES
            )
            creds = flow.run_local_server(port=0)
        TOKEN_FILE.write_text(creds.to_json())
    return creds


def get_sheet_name(service, spreadsheet_id: str, gid: int) -> str:
    """Look up the tab name for a given gid."""
    meta = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    for sheet in meta["sheets"]:
        if sheet["properties"]["sheetId"] == gid:
            return sheet["properties"]["title"]
    raise ValueError(f"No sheet found with gid={gid}")


def append_transactions(transactions: list[Transaction]) -> int:
    """Append transactions to the sheet. Returns number of rows written."""
    creds = _get_credentials()
    service = build("sheets", "v4", credentials=creds)
    sheet_name = get_sheet_name(service, SPREADSHEET_ID, SHEET_GID)

    rows = [build_row(t) for t in transactions]
    if not rows:
        return 0

    service.spreadsheets().values().append(
        spreadsheetId=SPREADSHEET_ID,
        range=f"'{sheet_name}'!A:K",
        valueInputOption="USER_ENTERED",
        insertDataOption="INSERT_ROWS",
        body={"values": rows},
    ).execute()

    return len(rows)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_sheets_writer.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add sheets_writer.py tests/test_sheets_writer.py
git commit -m "feat: Google Sheets writer"
```

---

## Task 5: Main CLI script

**Files:**
- Create: `main.py`

- [ ] **Step 1: Write `main.py`**

```python
#!/usr/bin/env python3
# main.py
"""
Usage:
    python main.py statement.pdf --card "Chase Sapphire" --year 2026
    python main.py *.pdf --card "Chase Sapphire"  # multiple PDFs
"""
import argparse
from datetime import date

from date_filter import billing_window, in_window
from pdf_parser import parse_pdf
from sheets_writer import append_transactions


def main():
    parser = argparse.ArgumentParser(
        description="Copy credit card PDF transactions to Google Sheets."
    )
    parser.add_argument("pdfs", nargs="+", help="Path(s) to PDF statement(s)")
    parser.add_argument("--card", required=True, help='Card name, e.g. "Chase Sapphire"')
    parser.add_argument(
        "--year",
        type=int,
        default=date.today().year,
        help="Year for MM/DD dates in the statement (default: current year)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print rows without writing to the sheet",
    )
    args = parser.parse_args()

    start, end = billing_window()
    print(f"Billing window: {start} → {end}")

    all_transactions = []
    for pdf_path in args.pdfs:
        print(f"Parsing {pdf_path}...")
        txns = parse_pdf(pdf_path, card_name=args.card, year=args.year)
        in_range = [t for t in txns if in_window(t.date, start, end)]
        print(f"  Found {len(txns)} transactions, {len(in_range)} in window")
        all_transactions.extend(in_range)

    if not all_transactions:
        print("No transactions to write.")
        return

    # Sort oldest → newest
    all_transactions.sort(key=lambda t: t.date)

    print(f"\n{'DRY RUN — ' if args.dry_run else ''}Writing {len(all_transactions)} rows:")
    for t in all_transactions:
        print(f"  {t.date}  {t.description:<40}  ${t.amount:.2f}")

    if not args.dry_run:
        written = append_transactions(all_transactions)
        print(f"\nWrote {written} rows to Google Sheet.")
    else:
        print("\n(Dry run — nothing written)")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Smoke test with dry run**

```bash
python main.py path/to/your-statement.pdf --card "Chase Sapphire" --dry-run
```

Expected: prints billing window, transaction count, and table of rows without writing.

- [ ] **Step 3: Commit**

```bash
git add main.py
git commit -m "feat: main CLI script"
```

---

## Task 6: End-to-end test against the real sheet

- [ ] **Step 1: First OAuth run (browser will open)**

```bash
python main.py path/to/your-statement.pdf --card "Chase Sapphire" --dry-run
```

A browser tab opens asking you to authorize access to Google Sheets. Approve it. `token.json` is created. Subsequent runs will not prompt.

- [ ] **Step 2: Verify dry-run output looks correct**

Check that dates, descriptions, and amounts match what you see in the PDF. Confirm the billing window matches the dates you expect.

- [ ] **Step 3: Write to the sheet**

```bash
python main.py path/to/your-statement.pdf --card "Chase Sapphire"
```

- [ ] **Step 4: Verify in the sheet**

Open https://docs.google.com/spreadsheets/d/YOUR_SPREADSHEET_ID/edit?gid=0 and confirm:
- New rows appear at the bottom
- Column A has the correct dates
- Column B has the correct amounts
- Column C has merchant names
- Column E has checkboxes checked
- Column G has the card name
- Column K says "Automated by Claude"

- [ ] **Step 5: Final commit**

```bash
git add .
git commit -m "chore: verified end-to-end"
```

---

## Self-review

**Spec coverage:**
- ✅ Copies transactions from credit card PDFs → `parse_pdf`
- ✅ Filters 16th of last month – 15th of current month → `billing_window` + `in_window`
- ✅ One row per transaction → `append_transactions` iterates `build_row` per txn
- ✅ Writes to the specific Google Sheet → `SPREADSHEET_ID` + `SHEET_GID` hardcoded
- ✅ Same column layout as existing amazon workflow → verified against `log-amazon-transactions.md`

**Placeholder scan:** None found. All code steps contain full implementations.

**Type consistency:**
- `Transaction.date` is `datetime.date` throughout — used in `build_row`, `in_window`, sorting.
- `parse_transactions` and `parse_pdf` both return `list[Transaction]`.
- `build_row` returns `list` of 11 elements — consistent with `append_transactions`.
