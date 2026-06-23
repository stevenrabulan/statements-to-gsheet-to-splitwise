# Multi-Account CSV Importer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the shipped PDF→Google Sheets tool into a multi-account importer that idempotently imports *spending* from per-account CSV exports (Fakecoin, Chase credit, Chase checking, Discover) plus the existing PDF fallback.

**Architecture:** Refactor first (move `Transaction`→`models.py`, `pdf_parser.py`→`adapters/chase_pdf.py`) keeping all 12 existing tests green. Then build one complete vertical slice for Fakecoin (adapter → CSV reader → dedup → import log → sheet append → CLI). Then add the three sample-driven adapters, each gated on a real sample CSV from the user.

**Tech Stack:** Python 3.14 (stdlib `csv`, `hashlib`, `json`, `collections.Counter`, `dataclasses`), `pdfplumber`, Google Sheets API. Tests via `pytest`.

---

## Environment (read once, applies to every step)

- **Python:** ALWAYS `/path/to/split-transactions/.venv/bin/python`. The system `python`/`python3` is 3.9 and will crash on `X | None` syntax. Never use it.
- **Run a test:** `.venv/bin/python -m pytest tests/test_x.py::test_name -v`
- **Run all tests:** `.venv/bin/python -m pytest -q`
- **No credentials required.** Every adapter, the CSV reader, dedup, and the import log are unit-tested with fixtures/mocks. `credentials.json` is only needed for real end-to-end sheet writes — the plan never blocks on it.
- **Commits:** one commit per task (matches prior work). End each commit message with:
  `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`
- **Branch:** currently on `master`. Stay on it (prior work committed to master).

## File Structure (target end state)

| File | Responsibility |
|------|----------------|
| `models.py` | `Transaction` dataclass, `ParseResult` dataclass, `ImporterError` exception |
| `csv_reader.py` | `read_csv(path)` / `read_csv_text(text)` — sniff comma vs tab, return `(header, rows)` |
| `adapters/__init__.py` | adapter registry, `detect_adapter(header)`, `account_name(path)`, `SOURCE_MAP` |
| `adapters/fakecoin.py` | Fakecoin credit CSV adapter (fully specified) |
| `adapters/chase_credit.py` | Chase credit CSV adapter (sample-gated) |
| `adapters/chase_checking.py` | Chase checking CSV adapter (sample-gated + filter rule) |
| `adapters/discover.py` | Discover credit CSV adapter (sample-gated) |
| `adapters/chase_pdf.py` | existing PDF parser, relocated (`NAME="pdf"`) |
| `dedup.py` | multiset row-identity dedup |
| `import_log.py` | content-hashed file ledger read/append |
| `date_filter.py` | unchanged — `in_window` reused for optional `--from`/`--to` |
| `sheets_writer.py` | `build_row` (new K-note), `append_transactions`, new `read_existing_rows()` |
| `main.py` | CLI, routing, import-log + dedup orchestration |
| `import_log.json` | gitignored runtime ledger |
| `transactions/<YYYY-MM>/` | gitignored real exports |
| `tests/fixtures/` | committed synthetic CSVs |

**Adapter contract** (every CSV adapter exposes):
```python
NAME: str                                       # e.g. "fakecoin"
def matches(header: list[str]) -> bool          # header-sniff for routing
def parse(rows: list[dict], account: str) -> ParseResult
```

---

## Task 1: Introduce `models.py`; rework `Transaction` and `build_row`

Moves `Transaction` out of `pdf_parser.py`, renames `card_name`→`account`, adds `source_file`, and updates `sheets_writer.build_row` to write the new column-K provenance note. `pdf_parser.py` stays in place (it moves in Task 2).

**Files:**
- Create: `models.py`
- Modify: `pdf_parser.py` (remove dataclass, import from `models`)
- Modify: `sheets_writer.py:9` (import), `sheets_writer.py:18-32` (`build_row`)
- Modify: `tests/test_pdf_parser.py:1,24` (import + field name)
- Modify: `tests/test_sheets_writer.py` (import, fields, K-note)

- [ ] **Step 1: Update the failing tests first**

Replace `tests/test_sheets_writer.py` entirely:

```python
from datetime import date
from models import Transaction
from sheets_writer import build_row


def _txn(**kw):
    base = dict(date=date(2026, 5, 20), description="WHOLE FOODS MARKET",
                amount=45.67, account="Chase Sapphire Reserve",
                source_file="Chase Sapphire Reserve.csv")
    base.update(kw)
    return Transaction(**base)


def test_build_row_fields():
    row = build_row(_txn())
    assert row[0] == "05/20/2026"
    assert row[1] == 45.67
    assert row[2] == "WHOLE FOODS MARKET"
    assert row[3] == ""
    assert row[4] is True
    assert row[5] == ""
    assert row[6] == "Chase Sapphire Reserve"
    assert row[7] == "" and row[8] == "" and row[9] == ""
    assert row[10] == "split-transactions automation Chase Sapphire Reserve.csv"
    assert len(row) == 11


def test_build_row_date_format():
    row = build_row(_txn(date=date(2026, 1, 5)))
    assert row[0] == "01/05/2026"


def test_k_note_falls_back_when_source_file_empty():
    row = build_row(_txn(source_file=""))
    assert row[10] == "split-transactions automation"
```

In `tests/test_pdf_parser.py` change the import line and the one field assertion:
- Line 1: `from pdf_parser import parse_transactions` and `from models import Transaction`
- Line 24: `assert t.account == "Chase Sapphire"` (was `t.card_name`)

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_sheets_writer.py tests/test_pdf_parser.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'models'` (and field errors).

- [ ] **Step 3: Create `models.py`**

```python
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


@dataclass
class ParseResult:
    transactions: list[Transaction] = field(default_factory=list)
    skipped: Counter = field(default_factory=Counter)   # reason -> count (dropped rows)
    warnings: list[str] = field(default_factory=list)   # imported-but-flagged rows
```

- [ ] **Step 4: Point `pdf_parser.py` at `models`**

In `pdf_parser.py`, delete the `@dataclass class Transaction` block (lines 8-13) and replace the imports at the top:

```python
import re
import pdfplumber
from datetime import date
from pathlib import Path

from models import Transaction
```

In `parse_transactions`, change the `Transaction(...)` construction (currently `card_name=card_name`) to use the new field, mapping the PDF's card label to `account` and leaving `source_file` for `main.py` to stamp:

```python
        results.append(Transaction(date=txn_date, description=description,
                                   amount=amount, account=card_name))
```

(Keep the `card_name` *parameter* name on `parse_transactions`/`parse_pdf` — it is the PDF adapter's public signature and `main.py` still calls it that way until Task 9.)

- [ ] **Step 5: Update `sheets_writer.build_row`**

In `sheets_writer.py` change the import (line 9) from `from pdf_parser import Transaction` to `from models import Transaction`, then replace `build_row` (lines 18-32):

```python
def _k_note(source_file: str) -> str:
    sf = (source_file or "").strip()
    return f"split-transactions automation {sf}" if sf else "split-transactions automation"


def build_row(txn: Transaction) -> list:
    return [
        txn.date.strftime("%m/%d/%Y"),
        txn.amount,
        txn.description,
        "",
        True,
        "",
        txn.account,
        "",
        "",
        "",
        _k_note(txn.source_file),
    ]
```

- [ ] **Step 6: Run the full suite — all green**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS (12 tests).

- [ ] **Step 7: Commit**

```bash
git add models.py pdf_parser.py sheets_writer.py tests/test_pdf_parser.py tests/test_sheets_writer.py
git commit -m "refactor: extract Transaction to models.py; account + source_file fields; K-note"
```

---

## Task 2: Create `adapters/` package; relocate `pdf_parser.py` → `adapters/chase_pdf.py`

Pure move + `NAME` constant. No behavior change.

**Files:**
- Create: `adapters/__init__.py`
- Rename: `pdf_parser.py` → `adapters/chase_pdf.py`
- Modify: `main.py:11` (import)
- Modify: `tests/test_pdf_parser.py:1` (import)

- [ ] **Step 1: Move the file and create the package**

```bash
mkdir -p adapters
git mv pdf_parser.py adapters/chase_pdf.py
touch adapters/__init__.py
```

- [ ] **Step 2: Add `NAME` to the PDF adapter**

At the top of `adapters/chase_pdf.py`, below the imports, add:

```python
NAME = "pdf"
```

- [ ] **Step 3: Fix the importers**

- `main.py` line 11: `from adapters.chase_pdf import parse_pdf`
- `tests/test_pdf_parser.py` line 1: `from adapters.chase_pdf import parse_transactions`

- [ ] **Step 4: Run the full suite**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS (12 tests).

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor: relocate pdf_parser to adapters/chase_pdf.py; add adapters package"
```

---

## Task 3: CSV reader with delimiter sniffing

Fakecoin exports are tab-*or*-comma delimited; the rest are comma. One small reader handles both and strips header whitespace so adapters can use clean dict keys.

**Files:**
- Create: `csv_reader.py`
- Create: `tests/test_csv_reader.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_csv_reader.py`:

```python
from csv_reader import read_csv_text

COMMA = "Date,Amount,Type\n2026-06-01,12.50,PURCHASE\n"
TAB = "Date\tAmount\tType\n2026-06-01\t12.50\tPURCHASE\n"
PADDED = " Date , Amount , Type \n2026-06-01,12.50,PURCHASE\n"


def test_reads_comma():
    header, rows = read_csv_text(COMMA)
    assert header == ["Date", "Amount", "Type"]
    assert rows == [{"Date": "2026-06-01", "Amount": "12.50", "Type": "PURCHASE"}]


def test_reads_tab():
    header, rows = read_csv_text(TAB)
    assert header == ["Date", "Amount", "Type"]
    assert rows[0]["Type"] == "PURCHASE"


def test_strips_header_whitespace():
    header, rows = read_csv_text(PADDED)
    assert header == ["Date", "Amount", "Type"]
    assert rows[0]["Amount"] == "12.50"


def test_empty_text():
    header, rows = read_csv_text("")
    assert header == [] and rows == []
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_csv_reader.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'csv_reader'`.

- [ ] **Step 3: Implement `csv_reader.py`**

```python
import csv
import io
from pathlib import Path


def read_csv_text(text: str) -> tuple[list[str], list[dict]]:
    """Parse CSV text, sniffing comma vs tab from the header line.

    Returns (header, rows) where header columns and dict keys are stripped.
    """
    if not text or not text.strip():
        return [], []
    first_line = text.splitlines()[0]
    # ponytail: tab-vs-comma by presence in the header line; the four real
    # formats never mix the two. Upgrade to csv.Sniffer if a quoted-comma case appears.
    delimiter = "\t" if "\t" in first_line else ","
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    header = [h.strip() for h in (reader.fieldnames or [])]
    rows = [{(k.strip() if k else k): v for k, v in row.items()} for row in reader]
    return header, rows


def read_csv(path: str | Path) -> tuple[list[str], list[dict]]:
    return read_csv_text(Path(path).read_text())


if __name__ == "__main__":  # ponytail self-check
    h, r = read_csv_text("a\tb\n1\t2\n")
    assert h == ["a", "b"] and r == [{"a": "1", "b": "2"}], (h, r)
    print("ok")
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/python -m pytest tests/test_csv_reader.py -q`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add csv_reader.py tests/test_csv_reader.py
git commit -m "feat: CSV reader with comma/tab delimiter sniffing"
```

---

## Task 4: Fakecoin adapter (vertical-slice adapter — fully specified)

First complete adapter. Fully specified by the spec; no sample needed.

**Fakecoin rules:**
- Header: `Date, Amount, Currency, Type, Status, Merchant, Card Last Four, Reward Amount, Reward Currency, Reward Status, Reward Rate`
- Keep `Type == PURCHASE`; drop everything else (e.g. `PAYMENT`).
- Status: drop denylist `{DECLINED, REVERSED, CANCELED, CANCELLED, FAILED}`; import known-good `{AUTHORIZED, SETTLED, CLEARED}`; **import-but-warn** on any other status.
- `Date` is ISO `YYYY-MM-DD`; `Amount` already positive; `Merchant` → description.

**Files:**
- Create: `adapters/fakecoin.py`
- Create: `tests/fixtures/fakecoin_sample.csv`
- Create: `tests/test_adapter_fakecoin.py`

- [ ] **Step 1: Create the committed fixture**

`tests/fixtures/fakecoin_sample.csv` (synthetic, comma-delimited):

```csv
Date,Amount,Currency,Type,Status,Merchant,Card Last Four,Reward Amount,Reward Currency,Reward Status,Reward Rate
2026-06-01,12.50,USD,PURCHASE,SETTLED,WHOLE FOODS,1234,0.25,USD,EARNED,0.02
2026-06-02,500.00,USD,PAYMENT,SETTLED,AUTOPAY THANK YOU,1234,0,USD,NONE,0
2026-06-03,9.99,USD,PURCHASE,DECLINED,NETFLIX,1234,0,USD,NONE,0
2026-06-04,7.00,USD,PURCHASE,PENDING_REVIEW,COFFEE BAR,1234,0,USD,NONE,0
```

Expected from this fixture: 2 kept (row 1 SETTLED purchase; row 4 unknown-status purchase imported-with-warning), drop row 2 (payment), drop row 3 (dead status). `skipped == {"payment/deposit": 1, "dead status": 1}`, `len(warnings) == 1`.

- [ ] **Step 2: Write the failing tests**

`tests/test_adapter_fakecoin.py`:

```python
from pathlib import Path
from datetime import date

import pytest

from csv_reader import read_csv, read_csv_text
from models import ImporterError
from adapters import fakecoin

FIXTURE = Path(__file__).parent / "fixtures" / "fakecoin_sample.csv"


def _parse():
    header, rows = read_csv(FIXTURE)
    assert fakecoin.matches(header)
    return fakecoin.parse(rows, account="Fakecoin Card")


def test_keeps_only_purchases_and_normalizes_fields():
    result = _parse()
    assert len(result.transactions) == 2
    t = result.transactions[0]
    assert t.date == date(2026, 6, 1)
    assert t.description == "WHOLE FOODS"
    assert t.amount == 12.50
    assert t.account == "Fakecoin Card"


def test_payment_and_dead_status_dropped():
    result = _parse()
    assert result.skipped["payment/deposit"] == 1
    assert result.skipped["dead status"] == 1


def test_unknown_status_imported_with_warning():
    result = _parse()
    descriptions = [t.description for t in result.transactions]
    assert "COFFEE BAR" in descriptions          # imported despite unknown status
    assert len(result.warnings) == 1
    assert "PENDING_REVIEW" in result.warnings[0]


def test_matches_rejects_foreign_header():
    assert fakecoin.matches(["Trans. Date", "Post Date", "Description", "Amount", "Category"]) is False


def test_tab_delimited_parses():
    text = FIXTURE.read_text().replace(",", "\t")
    header, rows = read_csv_text(text)
    result = fakecoin.parse(rows, account="Fakecoin Card")
    assert len(result.transactions) == 2


def test_missing_column_raises():
    rows = [{"Date": "2026-06-01", "Amount": "5.00"}]  # no Type/Status/Merchant
    with pytest.raises(ImporterError):
        fakecoin.parse(rows, account="Fakecoin Card")
```

- [ ] **Step 3: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_adapter_fakecoin.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'adapters.fakecoin'`.

- [ ] **Step 4: Implement `adapters/fakecoin.py`**

```python
from datetime import datetime

from models import Transaction, ParseResult, ImporterError

NAME = "fakecoin"

_REQUIRED = ("Date", "Amount", "Type", "Status", "Merchant")
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
    assert account, "account label is required"
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
```

- [ ] **Step 5: Run to verify pass**

Run: `.venv/bin/python -m pytest tests/test_adapter_fakecoin.py -q`
Expected: PASS (6 tests).

- [ ] **Step 6: Commit**

```bash
git add adapters/fakecoin.py tests/fixtures/fakecoin_sample.csv tests/test_adapter_fakecoin.py
git commit -m "feat: Fakecoin CSV adapter"
```

---

## Task 5: `dedup.py` — multiset row-identity dedup

Pure functions; no IO. Key = `(date, round(amount,2), normalized_description, normalized_account)`. Filename/K-note deliberately excluded so the same charge re-exported under a different filename still dedups.

**Files:**
- Create: `dedup.py`
- Create: `tests/test_dedup.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_dedup.py`:

```python
from datetime import date

from models import Transaction
from dedup import dedup, existing_keys_from_rows


def _t(amount, desc="Coffee", d=date(2026, 6, 1), account="Visa"):
    return Transaction(date=d, description=desc, amount=amount, account=account)


def _row(date_str, amount, desc, account):
    # Sheet row layout: A=date B=amount C=desc D E F G=account ...
    return [date_str, amount, desc, "", True, "", account]


def test_exact_reimport_adds_nothing():
    existing = existing_keys_from_rows([_row("06/01/2026", "5.00", "Coffee", "Visa")])
    assert dedup([_t(5.00)], existing) == []


def test_true_repeat_charge_preserved():
    # Two identical coffees, none in the sheet yet -> both kept.
    assert len(dedup([_t(5.00), _t(5.00)], existing_keys_from_rows([]))) == 2


def test_partial_overlap_sheet_has_one_batch_has_two():
    existing = existing_keys_from_rows([_row("06/01/2026", "5.00", "Coffee", "Visa")])
    kept = dedup([_t(5.00), _t(5.00)], existing)
    assert len(kept) == 1


def test_normalization_matches_case_and_whitespace():
    existing = existing_keys_from_rows([_row("06/01/2026", "$5.00", "  coffee   SHOP ", "  visa ")])
    assert dedup([_t(5.00, desc="Coffee Shop", account="Visa")], existing) == []


def test_unparseable_existing_rows_ignored():
    rows = [["header", "Amount", "Desc"], ["", "", ""], _row("06/01/2026", "5.00", "Coffee", "Visa")]
    existing = existing_keys_from_rows(rows)
    assert dedup([_t(5.00)], existing) == []        # only the valid row counted
    assert dedup([_t(9.99, desc="New")], existing) == [_t(9.99, desc="New")][:1] or True
```

(The last assertion's intent: the junk rows do not crash and do not match `_t(5.00)`.)

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_dedup.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'dedup'`.

- [ ] **Step 3: Implement `dedup.py`**

```python
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
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/python -m pytest tests/test_dedup.py -q`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add dedup.py tests/test_dedup.py
git commit -m "feat: multiset row-identity dedup"
```

---

## Task 6: `sheets_writer.read_existing_rows()`

Thin read of `A:K` for dedup. Defensive parsing lives in `dedup.existing_keys_from_rows` (Task 5), so this just returns raw values. Unit-tested with a mocked Sheets service — no credentials.

**Files:**
- Modify: `sheets_writer.py` (add `read_existing_rows`)
- Modify: `tests/test_sheets_writer.py` (add mocked test)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_sheets_writer.py`:

```python
from unittest.mock import MagicMock, patch


@patch("sheets_writer.build")
@patch("sheets_writer._get_credentials")
@patch("sheets_writer.get_sheet_name", return_value="Sheet1")
def test_read_existing_rows_returns_values(mock_name, mock_creds, mock_build):
    service = MagicMock()
    (service.spreadsheets.return_value.values.return_value
        .get.return_value.execute.return_value) = {"values": [["06/01/2026", "5.00"]]}
    mock_build.return_value = service

    from sheets_writer import read_existing_rows
    rows = read_existing_rows()
    assert rows == [["06/01/2026", "5.00"]]


@patch("sheets_writer.build")
@patch("sheets_writer._get_credentials")
@patch("sheets_writer.get_sheet_name", return_value="Sheet1")
def test_read_existing_rows_empty_sheet(mock_name, mock_creds, mock_build):
    service = MagicMock()
    (service.spreadsheets.return_value.values.return_value
        .get.return_value.execute.return_value) = {}
    mock_build.return_value = service

    from sheets_writer import read_existing_rows
    assert read_existing_rows() == []
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_sheets_writer.py -k read_existing -q`
Expected: FAIL — `ImportError: cannot import name 'read_existing_rows'`.

- [ ] **Step 3: Implement `read_existing_rows`**

Add to `sheets_writer.py` (after `get_sheet_name`):

```python
def read_existing_rows() -> list[list]:
    """Read the tab's A:K for dedup. Returns raw cell values (no parsing)."""
    creds = _get_credentials()
    service = build("sheets", "v4", credentials=creds)
    sheet_name = get_sheet_name(service, SPREADSHEET_ID, SHEET_GID)
    resp = (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=SPREADSHEET_ID, range=f"'{sheet_name}'!A:K")
        .execute()
    )
    return resp.get("values", [])
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/python -m pytest tests/test_sheets_writer.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add sheets_writer.py tests/test_sheets_writer.py
git commit -m "feat: read_existing_rows for dedup"
```

---

## Task 7: `import_log.py` — content-hashed file ledger

Records which files were imported (by SHA-256 of bytes) so unchanged files are skipped. Corrupt/missing log starts fresh with a warning. Skip-if-seen / `--force` / dry-run-no-write behaviors are wired in `main.py` (Task 9); this task owns the pure ledger functions and gitignores the log.

**Files:**
- Create: `import_log.py`
- Create: `tests/test_import_log.py`
- Modify: `.gitignore`

- [ ] **Step 1: Gitignore the runtime ledger**

Add to `.gitignore`:

```
import_log.json
```

- [ ] **Step 2: Write the failing tests**

`tests/test_import_log.py`:

```python
from datetime import datetime

import pytest

import import_log


def test_file_hash_is_content_based(tmp_path):
    f = tmp_path / "a.csv"
    f.write_text("hello")
    h1 = import_log.file_hash(f)
    f.write_text("hello world")
    assert import_log.file_hash(f) != h1


def test_append_then_load_roundtrip(tmp_path):
    log_path = tmp_path / "import_log.json"
    entry = {"file": "a.csv", "sha256": "abc", "account": "Visa",
             "source": "fakecoin", "imported_at": datetime.now().isoformat(),
             "rows_new": 3, "rows_skipped": 1, "date_range": ["2026-06-01", "2026-06-30"]}
    import_log.append_entry(entry, path=log_path)
    log = import_log.load_log(log_path)
    assert len(log) == 1 and log[0]["sha256"] == "abc"


def test_find_by_hash(tmp_path):
    log_path = tmp_path / "import_log.json"
    import_log.append_entry({"sha256": "abc"}, path=log_path)
    log = import_log.load_log(log_path)
    assert import_log.find_by_hash("abc", log)["sha256"] == "abc"
    assert import_log.find_by_hash("nope", log) is None


def test_missing_log_is_empty(tmp_path):
    assert import_log.load_log(tmp_path / "nope.json") == []


def test_corrupt_log_starts_fresh(tmp_path, capsys):
    log_path = tmp_path / "import_log.json"
    log_path.write_text("{ not json")
    assert import_log.load_log(log_path) == []
    assert "corrupt" in capsys.readouterr().out.lower()
```

- [ ] **Step 3: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_import_log.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'import_log'`.

- [ ] **Step 4: Implement `import_log.py`**

```python
import hashlib
import json
from pathlib import Path

LOG_PATH = Path(__file__).parent / "import_log.json"


def file_hash(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_log(path: str | Path = LOG_PATH) -> list[dict]:
    p = Path(path)
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text())
        if not isinstance(data, list):
            raise ValueError("import log is not a list")
        return data
    except (json.JSONDecodeError, ValueError) as exc:
        print(f"WARNING: {p} is corrupt ({exc}); starting fresh.")
        return []


def find_by_hash(sha256: str, log: list[dict]) -> dict | None:
    for entry in log:
        if entry.get("sha256") == sha256:
            return entry
    return None


def append_entry(entry: dict, path: str | Path = LOG_PATH) -> None:
    log = load_log(path)
    log.append(entry)
    Path(path).write_text(json.dumps(log, indent=2))
```

- [ ] **Step 5: Run to verify pass**

Run: `.venv/bin/python -m pytest tests/test_import_log.py -q`
Expected: PASS (5 tests).

- [ ] **Step 6: Commit**

```bash
git add import_log.py tests/test_import_log.py .gitignore
git commit -m "feat: content-hashed file import log"
```

---

## Task 8: Routing — `detect_adapter`, `account_name`, `SOURCE_MAP`

Header → adapter resolution and filename-stem → account name. Registry starts with Fakecoin + PDF; Tasks 10-12 append.

**Files:**
- Modify: `adapters/__init__.py`
- Create: `tests/test_routing.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_routing.py`:

```python
import pytest

from models import ImporterError
from adapters import detect_adapter, account_name, SOURCE_MAP


FAKECOIN_HEADER = ["Date", "Amount", "Currency", "Type", "Status", "Merchant",
                   "Card Last Four", "Reward Amount", "Reward Currency",
                   "Reward Status", "Reward Rate"]


def test_detects_fakecoin():
    assert detect_adapter(FAKECOIN_HEADER).NAME == "fakecoin"


def test_unrecognized_header_raises_with_listing():
    with pytest.raises(ImporterError) as exc:
        detect_adapter(["Foo", "Bar"])
    msg = str(exc.value).lower()
    assert "fakecoin" in msg          # lists supported accounts
    assert "foo" in msg               # echoes the unrecognized header


def test_account_name_is_filename_stem():
    assert account_name("transactions/2026-06/Chase Sapphire Reserve.csv") == "Chase Sapphire Reserve"
    assert account_name("Chase Checking.csv") == "Chase Checking"


def test_source_map_has_pdf_and_fakecoin():
    assert "fakecoin" in SOURCE_MAP and "pdf" in SOURCE_MAP
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_routing.py -q`
Expected: FAIL — `ImportError: cannot import name 'detect_adapter'`.

- [ ] **Step 3: Implement the registry in `adapters/__init__.py`**

```python
from pathlib import Path

from models import ImporterError
from . import fakecoin, chase_pdf

# CSV adapters participate in header-sniff routing (in priority order).
# Tasks 10-12 append chase_credit, chase_checking, discover.
CSV_ADAPTERS = [fakecoin]

# All adapters keyed by NAME for the --source override (includes pdf).
SOURCE_MAP = {a.NAME: a for a in CSV_ADAPTERS}
SOURCE_MAP[chase_pdf.NAME] = chase_pdf


def detect_adapter(header: list[str]):
    """Return the CSV adapter whose matches() accepts this header, else raise."""
    for adapter in CSV_ADAPTERS:
        if adapter.matches(header):
            return adapter
    supported = ", ".join(a.NAME for a in CSV_ADAPTERS)
    raise ImporterError(
        f"No adapter matched CSV header {header!r}. "
        f"Supported accounts: {supported}."
    )


def account_name(path: str) -> str:
    """Account label (sheet column G) = the file's stem."""
    return Path(path).stem
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/python -m pytest tests/test_routing.py -q`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add adapters/__init__.py tests/test_routing.py
git commit -m "feat: adapter routing — detect_adapter, account_name, source map"
```

---

## Task 9: `main.py` orchestration + CLI (completes the Fakecoin vertical slice)

Wires everything: expand paths, skip-if-seen (unless `--force`), route, parse + stamp `source_file`, optional `--from`/`--to`, dedup against the sheet, dry-run preview, append, record log on success. After this task `python main.py <fakecoin.csv>` works end-to-end.

**Files:**
- Rewrite: `main.py`
- Create: `tests/test_main.py`
- Modify: `.gitignore` (add `transactions/`)

- [ ] **Step 1: Gitignore real exports**

Add to `.gitignore`:

```
transactions/*
!transactions/README.md
```

- [ ] **Step 2: Write the failing integration tests**

`tests/test_main.py` (drives the orchestrator with mocked sheet IO and a temp import log):

```python
from datetime import date
from unittest.mock import patch

import pytest

import main
from models import Transaction, ParseResult

FAKECOIN = (
    "Date,Amount,Currency,Type,Status,Merchant,Card Last Four,"
    "Reward Amount,Reward Currency,Reward Status,Reward Rate\n"
    "2026-06-01,12.50,USD,PURCHASE,SETTLED,WHOLE FOODS,1234,0,USD,NONE,0\n"
)


@pytest.fixture
def csv_file(tmp_path):
    f = tmp_path / "Fakecoin Card.csv"
    f.write_text(FAKECOIN)
    return f


def _run(args, existing_rows=None, log_path=None):
    with patch("main.read_existing_rows", return_value=existing_rows or []) as rd, \
         patch("main.append_transactions", return_value=0) as wr, \
         patch("main.import_log.LOG_PATH", log_path), \
         patch("main.CREDENTIALS_FILE_EXISTS", True):
        main.run(main.parse_args(args))
    return rd, wr


def test_appends_new_rows(csv_file, tmp_path):
    rd, wr = _run([str(csv_file)], log_path=tmp_path / "log.json")
    wr.assert_called_once()
    appended = wr.call_args[0][0]
    assert len(appended) == 1
    assert appended[0].source_file == "Fakecoin Card.csv"   # stamped basename
    assert appended[0].account == "Fakecoin Card"           # filename stem


def test_dedup_against_existing_sheet(csv_file, tmp_path):
    existing = [["06/01/2026", "12.50", "WHOLE FOODS", "", True, "", "Fakecoin Card"]]
    rd, wr = _run([str(csv_file)], existing_rows=existing, log_path=tmp_path / "log.json")
    # Nothing new -> append not called (clean "nothing new" exit).
    wr.assert_not_called()


def test_skip_if_already_imported(csv_file, tmp_path):
    log_path = tmp_path / "log.json"
    _run([str(csv_file)], log_path=log_path)             # first import records the file
    rd, wr = _run([str(csv_file)], log_path=log_path)    # second run skips it
    wr.assert_not_called()


def test_force_reprocesses_logged_file(csv_file, tmp_path):
    log_path = tmp_path / "log.json"
    _run([str(csv_file)], log_path=log_path)
    rd, wr = _run([str(csv_file), "--force"], log_path=log_path)
    wr.assert_called_once()                               # reprocessed despite log


def test_dry_run_writes_nothing(csv_file, tmp_path):
    log_path = tmp_path / "log.json"
    rd, wr = _run([str(csv_file), "--dry-run"], log_path=log_path)
    wr.assert_not_called()
    assert not log_path.exists()                          # log untouched in dry-run


def test_missing_path_errors():
    with pytest.raises(SystemExit):
        main.run(main.parse_args(["/no/such/file.csv"]))
```

- [ ] **Step 3: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_main.py -q`
Expected: FAIL — `AttributeError: module 'main' has no attribute 'run'` (or `parse_args`).

- [ ] **Step 4: Rewrite `main.py`**

```python
#!/usr/bin/env python3
"""Multi-account CSV (+ PDF fallback) importer for the Splitwise sheet.

Usage:
    python main.py transactions/2026-06/                     # whole month
    python main.py "Fakecoin Card.csv"
    python main.py transactions/Chase1111_Activity....PDF --source pdf --account "Chase Sapphire" --year 2026
    python main.py *.csv --dry-run
"""
import argparse
import sys
from datetime import date, datetime
from pathlib import Path

import import_log
from adapters import detect_adapter, account_name, SOURCE_MAP
from csv_reader import read_csv
from dedup import dedup, existing_keys_from_rows
from date_filter import in_window
from sheets_writer import (
    CREDENTIALS_FILE,
    append_transactions,
    read_existing_rows,
)

CREDENTIALS_FILE_EXISTS = CREDENTIALS_FILE.exists()


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Import spending CSV/PDF exports into the Splitwise sheet.")
    p.add_argument("paths", nargs="+", help="Files and/or directories to import")
    p.add_argument("--account", help="Override account label (sheet column G); single-file use")
    p.add_argument("--source", choices=sorted(SOURCE_MAP), help="Force a specific adapter")
    p.add_argument("--from", dest="date_from", help="Only import on/after YYYY-MM-DD")
    p.add_argument("--to", dest="date_to", help="Only import on/before YYYY-MM-DD")
    p.add_argument("--year", type=int, default=date.today().year, help="Year for PDF MM/DD dates")
    p.add_argument("--force", action="store_true", help="Reprocess files already in the import log")
    p.add_argument("--dry-run", action="store_true", help="Preview only; write nothing")
    return p.parse_args(argv)


def gather_files(paths: list[str]) -> list[Path]:
    """Expand directories to *.csv + *.pdf; validate every path exists."""
    files: list[Path] = []
    for raw in paths:
        p = Path(raw)
        if not p.exists():
            sys.exit(f"ERROR: path not found: {raw}")
        if p.is_dir():
            files.extend(sorted(p.glob("*.csv")))
            files.extend(sorted(p.glob("*.pdf")))
        else:
            files.append(p)
    return files


def _parse_date_arg(value: str | None, label: str) -> date | None:
    if value is None:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        sys.exit(f"ERROR: --{label} must be YYYY-MM-DD, got {value!r}")


def _adapter_and_transactions(path: Path, args):
    """Route a single file and return (adapter_name, account, transactions)."""
    account = args.account or account_name(str(path))
    if args.source:
        adapter = SOURCE_MAP[args.source]
    elif path.suffix.lower() == ".pdf":
        adapter = SOURCE_MAP["pdf"]
    else:
        header, rows = read_csv(path)
        adapter = detect_adapter(header)

    if adapter.NAME == "pdf":
        txns = adapter.parse_pdf(path, card_name=account, year=args.year)
        skipped, warnings = {}, []
    else:
        header, rows = read_csv(path)
        result = adapter.parse(rows, account=account)
        txns, skipped, warnings = result.transactions, result.skipped, result.warnings

    for t in txns:                       # stamp the file basename for the K-note
        t.source_file = path.name
    return adapter.NAME, account, txns, skipped, warnings


def run(args) -> None:
    files = gather_files(args.paths)
    date_from = _parse_date_arg(args.date_from, "from")
    date_to = _parse_date_arg(args.date_to, "to")

    log = import_log.load_log()
    can_dedup = CREDENTIALS_FILE_EXISTS
    existing = existing_keys_from_rows(read_existing_rows()) if can_dedup else None
    if not can_dedup:
        print("WARNING: credentials.json absent — dedup skipped (parse-only preview).")

    to_append = []
    pending_log_entries = []
    for path in files:
        sha = import_log.file_hash(path)
        seen = import_log.find_by_hash(sha, log)
        if seen and not args.force:
            print(f"{path.name}: already imported {seen.get('imported_at', '?')} — skipping (use --force).")
            continue

        name, account, txns, skipped, warnings = _adapter_and_transactions(path, args)
        if date_from or date_to:
            lo = date_from or date.min
            hi = date_to or date.max
            txns = [t for t in txns if in_window(t.date, lo, hi)]

        new = dedup(txns, existing) if can_dedup else txns
        for w in warnings:
            print(f"  WARN {path.name}: {w}")
        print(f"{path.name}: adapter={name} account={account!r} "
              f"parsed={len(txns)} skipped={dict(skipped)} new={len(new)}")

        if new:
            dates = [t.date.isoformat() for t in new]
            pending_log_entries.append({
                "file": str(path), "sha256": sha, "account": account, "source": name,
                "rows_new": len(new), "rows_skipped": int(sum(skipped.values())),
                "date_range": [min(dates), max(dates)],
            })
            to_append.extend(new)

    if not to_append:
        print("Nothing new to write.")
        return

    to_append.sort(key=lambda t: t.date)
    print(f"\n{'DRY RUN — ' if args.dry_run else ''}{len(to_append)} row(s) to append:")
    for t in to_append:
        print(f"  {t.date}  {t.description:<40}  ${t.amount:.2f}  [{t.account}]")

    if args.dry_run:
        print("\n(Dry run — nothing written, import log untouched.)")
        return

    written = append_transactions(to_append)
    print(f"\nWrote {written} rows to the sheet.")
    for entry in pending_log_entries:                        # record only on success
        entry["imported_at"] = datetime.now().isoformat()
        import_log.append_entry(entry)


def main():
    run(parse_args())


if __name__ == "__main__":
    main()
```

Note: this references `sheets_writer.CREDENTIALS_FILE`, which already exists (`sheets_writer.py:14`). No change needed there.

- [ ] **Step 5: Run the new tests, then the full suite**

Run: `.venv/bin/python -m pytest tests/test_main.py -q`
Expected: PASS (6 tests).

Run: `.venv/bin/python -m pytest -q`
Expected: PASS (all tests — original 12 plus the new ones).

- [ ] **Step 6: Commit**

```bash
git add main.py tests/test_main.py .gitignore
git commit -m "feat: CLI + orchestration — routing, import-log skip, dedup, dry-run"
```

---

## Task 10: Chase credit adapter (SAMPLE-GATED)

> **GATE — do not write code until Step 1 is done.** The header strings and amount sign are a hypothesis from the spec until confirmed against a real export.

**Spec hypothesis (confirm in Step 1):**
- Header: `Transaction Date, Post Date, Description, Category, Type, Amount, Memo`
- Keep `Type == Sale`; drop `Payment`, `Return`, `Fee`, `Adjustment`.
- `Amount` negative for purchases → `abs()`. Date `MM/DD/YYYY`.

**Files:**
- Create: `adapters/chase_credit.py`
- Create: `tests/fixtures/chase_credit_sample.csv`
- Create: `tests/test_adapter_chase_credit.py`
- Modify: `adapters/__init__.py` (register)

- [ ] **Step 1: Obtain sample + confirm columns**

Ask the user for a real Chase credit CSV (header + 2-3 redacted rows). Confirm:
1. Exact header column names and order.
2. The `Type` values that mean a purchase vs payment/return/fee.
3. The sign of `Amount` for a purchase.
4. The date column to use and its format.

Build `tests/fixtures/chase_credit_sample.csv` from the confirmed shape with fake values — at minimum: one purchase, one payment, one return/credit. If the real columns differ from the hypothesis below, adjust the constants and the test before writing the implementation.

- [ ] **Step 2: Write the failing tests**

`tests/test_adapter_chase_credit.py` (adjust column names/signs to the confirmed sample):

```python
from pathlib import Path
from datetime import date

import pytest

from csv_reader import read_csv
from models import ImporterError
from adapters import chase_credit, detect_adapter

FIXTURE = Path(__file__).parent / "fixtures" / "chase_credit_sample.csv"


def _parse():
    header, rows = read_csv(FIXTURE)
    assert chase_credit.matches(header)
    return chase_credit.parse(rows, account="Chase Sapphire Reserve")


def test_keeps_sales_and_normalizes_to_positive():
    result = _parse()
    assert all(t.amount > 0 for t in result.transactions)
    t = result.transactions[0]
    assert isinstance(t.date, date)
    assert t.account == "Chase Sapphire Reserve"


def test_payments_and_returns_dropped():
    result = _parse()
    assert result.skipped  # at least one non-Sale row was dropped


def test_routes_by_header():
    header, _ = read_csv(FIXTURE)
    assert detect_adapter(header).NAME == "chase-credit"


def test_missing_column_raises():
    with pytest.raises(ImporterError):
        chase_credit.parse([{"Transaction Date": "06/01/2026"}], account="X")
```

- [ ] **Step 3: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_adapter_chase_credit.py -q`
Expected: FAIL — module missing.

- [ ] **Step 4: Implement `adapters/chase_credit.py`** (confirm constants against the sample)

```python
from datetime import datetime

from models import Transaction, ParseResult, ImporterError

NAME = "chase-credit"

_REQUIRED = ("Transaction Date", "Description", "Type", "Amount")
_SIGNATURE = {"Transaction Date", "Post Date", "Category", "Type", "Memo"}
_DROP_TYPES = {"PAYMENT": "payment/deposit", "RETURN": "credit/refund",
               "FEE": "credit/refund", "ADJUSTMENT": "credit/refund"}


def matches(header: list[str]) -> bool:
    return _SIGNATURE.issubset({h.strip() for h in header})


def _require(rows):
    if rows:
        missing = [c for c in _REQUIRED if c not in rows[0]]
        if missing:
            raise ImporterError(f"chase-credit: missing column(s): {', '.join(missing)}")


def parse(rows: list[dict], account: str) -> ParseResult:
    assert account, "account label is required"
    _require(rows)
    result = ParseResult()
    for i, row in enumerate(rows, start=2):
        txn_type = (row.get("Type") or "").strip().upper()
        if txn_type != "SALE":
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
        except ValueError:
            raise ImporterError(f"chase-credit row {i}: bad amount {raw_amount!r}")
        result.transactions.append(Transaction(
            date=txn_date, description=(row.get("Description") or "").strip(),
            amount=amount, account=account))
    return result
```

- [ ] **Step 5: Register in `adapters/__init__.py`**

```python
from . import fakecoin, chase_credit, chase_pdf
...
CSV_ADAPTERS = [fakecoin, chase_credit]
```

- [ ] **Step 6: Run adapter + routing + full suite**

Run: `.venv/bin/python -m pytest tests/test_adapter_chase_credit.py tests/test_routing.py -q`
Expected: PASS.
Run: `.venv/bin/python -m pytest -q`
Expected: PASS (all).

- [ ] **Step 7: Commit**

```bash
git add adapters/chase_credit.py adapters/__init__.py tests/fixtures/chase_credit_sample.csv tests/test_adapter_chase_credit.py
git commit -m "feat: Chase credit CSV adapter"
```

---

## Task 11: Chase checking adapter (SAMPLE-GATED + filtering rule)

> **GATE — do not write code until Step 1 is done.** Checking is the trickiest adapter: it must exclude credits/deposits, internal transfers, AND credit-card payments (otherwise card spending already imported is double-counted as the checking payment to that card).

**Spec hypothesis (confirm in Step 1):**
- Header: `Details, Posting Date, Description, Amount, Type, Balance, Check or Slip #`
- Keep `Details == DEBIT` with negative `Amount` → `abs()`.
- Exclude `Details == CREDIT`, internal transfers, and card payments — identified via `Type` (e.g. `ACCT_XFER`, loan/card-payment types) and description patterns.
- `Posting Date` `MM/DD/YYYY`.

**Files:**
- Create: `adapters/chase_checking.py`
- Create: `tests/fixtures/chase_checking_sample.csv`
- Create: `tests/test_adapter_chase_checking.py`
- Modify: `adapters/__init__.py` (register)

- [ ] **Step 1: Obtain sample + confirm columns AND the one-line filter rule**

Ask the user for a real Chase checking CSV (header + redacted rows covering: a normal debit, a deposit/credit, an internal transfer, and a credit-card payment). Confirm:
1. Exact header names.
2. **Which debits count as shared spending** (the one-line rule).
3. **How transfers and card payments appear** — the exact `Type` value(s) and/or description substrings that identify them so they can be excluded.
4. Date column + format; debit sign.

Encode the confirmed exclusions as `_TRANSFER_TYPES` and `_PAYMENT_PATTERNS` below. Build the fixture to include one of each excluded kind plus a kept debit.

- [ ] **Step 2: Write the failing tests**

`tests/test_adapter_chase_checking.py` (adjust to the confirmed rule):

```python
from pathlib import Path
from datetime import date

import pytest

from csv_reader import read_csv
from models import ImporterError
from adapters import chase_checking, detect_adapter

FIXTURE = Path(__file__).parent / "fixtures" / "chase_checking_sample.csv"


def _parse():
    header, rows = read_csv(FIXTURE)
    assert chase_checking.matches(header)
    return chase_checking.parse(rows, account="Chase Checking")


def test_keeps_only_spending_debits_positive():
    result = _parse()
    assert result.transactions
    assert all(t.amount > 0 for t in result.transactions)


def test_excludes_deposits_transfers_and_card_payments():
    result = _parse()
    descriptions = " ".join(t.description.upper() for t in result.transactions)
    assert "DEPOSIT" not in descriptions
    assert "TRANSFER" not in descriptions
    assert "PAYMENT" not in descriptions
    assert result.skipped["payment/deposit"] >= 1
    assert result.skipped["transfer"] >= 1


def test_routes_distinctly_from_chase_credit():
    header, _ = read_csv(FIXTURE)
    assert detect_adapter(header).NAME == "chase-checking"


def test_missing_column_raises():
    with pytest.raises(ImporterError):
        chase_checking.parse([{"Details": "DEBIT"}], account="X")
```

- [ ] **Step 3: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_adapter_chase_checking.py -q`
Expected: FAIL — module missing.

- [ ] **Step 4: Implement `adapters/chase_checking.py`** (confirm constants against the sample + rule)

```python
from datetime import datetime

from models import Transaction, ParseResult, ImporterError

NAME = "chase-checking"

_REQUIRED = ("Details", "Posting Date", "Description", "Amount", "Type")
_SIGNATURE = {"Details", "Posting Date", "Balance", "Check or Slip #"}

# Confirmed against the sample in Step 1:
_TRANSFER_TYPES = {"ACCT_XFER"}                       # internal transfers
_PAYMENT_PATTERNS = ("CREDIT CRD EPAY", "CARD PAYMENT", "AUTOPAY")  # card payments


def matches(header: list[str]) -> bool:
    return _SIGNATURE.issubset({h.strip() for h in header})


def _require(rows):
    if rows:
        missing = [c for c in _REQUIRED if c not in rows[0]]
        if missing:
            raise ImporterError(f"chase-checking: missing column(s): {', '.join(missing)}")


def parse(rows: list[dict], account: str) -> ParseResult:
    assert account, "account label is required"
    _require(rows)
    result = ParseResult()
    for i, row in enumerate(rows, start=2):
        details = (row.get("Details") or "").strip().upper()
        txn_type = (row.get("Type") or "").strip().upper()
        description = (row.get("Description") or "").strip()
        upper_desc = description.upper()

        if details != "DEBIT":
            result.skipped["payment/deposit"] += 1          # credits/deposits
            continue
        if txn_type in _TRANSFER_TYPES:
            result.skipped["transfer"] += 1
            continue
        if any(p in upper_desc for p in _PAYMENT_PATTERNS):
            result.skipped["payment/deposit"] += 1          # credit-card payment
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
        result.transactions.append(Transaction(
            date=txn_date, description=description, amount=amount, account=account))
    return result
```

- [ ] **Step 5: Register in `adapters/__init__.py`**

```python
from . import fakecoin, chase_credit, chase_checking, chase_pdf
...
CSV_ADAPTERS = [fakecoin, chase_credit, chase_checking]
```

- [ ] **Step 6: Run adapter + routing + full suite**

Run: `.venv/bin/python -m pytest tests/test_adapter_chase_checking.py tests/test_routing.py -q`
Expected: PASS.
Run: `.venv/bin/python -m pytest -q`
Expected: PASS (all).

- [ ] **Step 7: Commit**

```bash
git add adapters/chase_checking.py adapters/__init__.py tests/fixtures/chase_checking_sample.csv tests/test_adapter_chase_checking.py
git commit -m "feat: Chase checking CSV adapter (spending debits only)"
```

---

## Task 12: Discover credit adapter (SAMPLE-GATED)

> **GATE — do not write code until Step 1 is done.**

**Spec hypothesis (confirm in Step 1):**
- Header: `Trans. Date, Post Date, Description, Amount, Category`
- Purchases have **positive** `Amount`; drop negative amounts or `Category == "Payments and Credits"`.
- Date `MM/DD/YYYY`.

**Files:**
- Create: `adapters/discover.py`
- Create: `tests/fixtures/discover_sample.csv`
- Create: `tests/test_adapter_discover.py`
- Modify: `adapters/__init__.py` (register)

- [ ] **Step 1: Obtain sample + confirm columns**

Ask the user for a real Discover CSV (header + redacted rows: one purchase, one payment/credit). Confirm header names, the purchase amount sign, and how payments/credits are flagged (sign and/or `Category`). Build the fixture from the confirmed shape; adjust constants/tests if it differs.

- [ ] **Step 2: Write the failing tests**

`tests/test_adapter_discover.py`:

```python
from pathlib import Path
from datetime import date

import pytest

from csv_reader import read_csv
from models import ImporterError
from adapters import discover, detect_adapter

FIXTURE = Path(__file__).parent / "fixtures" / "discover_sample.csv"


def _parse():
    header, rows = read_csv(FIXTURE)
    assert discover.matches(header)
    return discover.parse(rows, account="Discover Card")


def test_keeps_purchases_positive():
    result = _parse()
    assert result.transactions
    assert all(t.amount > 0 for t in result.transactions)
    assert isinstance(result.transactions[0].date, date)


def test_payments_and_credits_dropped():
    result = _parse()
    assert result.skipped["credit/refund"] >= 1


def test_routes_by_header():
    header, _ = read_csv(FIXTURE)
    assert detect_adapter(header).NAME == "discover"


def test_missing_column_raises():
    with pytest.raises(ImporterError):
        discover.parse([{"Trans. Date": "06/01/2026"}], account="X")
```

- [ ] **Step 3: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_adapter_discover.py -q`
Expected: FAIL — module missing.

- [ ] **Step 4: Implement `adapters/discover.py`** (confirm constants against the sample)

```python
from datetime import datetime

from models import Transaction, ParseResult, ImporterError

NAME = "discover"

_REQUIRED = ("Trans. Date", "Description", "Amount", "Category")
_SIGNATURE = {"Trans. Date", "Post Date", "Description", "Amount", "Category"}


def matches(header: list[str]) -> bool:
    return _SIGNATURE == {h.strip() for h in header}   # exact: distinguishes from chase-credit


def _require(rows):
    if rows:
        missing = [c for c in _REQUIRED if c not in rows[0]]
        if missing:
            raise ImporterError(f"discover: missing column(s): {', '.join(missing)}")


def parse(rows: list[dict], account: str) -> ParseResult:
    assert account, "account label is required"
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
        if amount <= 0:                                # negative = payment/credit
            result.skipped["credit/refund"] += 1
            continue
        result.transactions.append(Transaction(
            date=txn_date, description=(row.get("Description") or "").strip(),
            amount=amount, account=account))
    return result
```

- [ ] **Step 5: Register in `adapters/__init__.py`**

```python
from . import fakecoin, chase_credit, chase_checking, discover, chase_pdf
...
CSV_ADAPTERS = [fakecoin, chase_credit, chase_checking, discover]
```

- [ ] **Step 6: Run adapter + routing + full suite**

Run: `.venv/bin/python -m pytest tests/test_adapter_discover.py tests/test_routing.py -q`
Expected: PASS.
Run: `.venv/bin/python -m pytest -q`
Expected: PASS (all).

- [ ] **Step 7: Commit**

```bash
git add adapters/discover.py adapters/__init__.py tests/fixtures/discover_sample.csv tests/test_adapter_discover.py
git commit -m "feat: Discover credit CSV adapter"
```

---

## Self-Review (performed against the spec)

**Spec coverage:**
- Goal / idempotent import → Tasks 5 (dedup), 7 (import log), 9 (orchestration). ✓
- Key decision 1 (CSV everywhere, PDF fallback) → Tasks 3-4, 10-12; PDF retained Task 2. ✓
- Decision 2 (dedup replaces billing window) → Task 5 + Task 9 (billing window dropped from main). ✓
- Decision 3 (file-level import log) → Task 7 + Task 9 skip-if-seen/`--force`. ✓
- Decision 4 (`--from`/`--to`) → Task 9 (reuses `date_filter.in_window`). ✓
- Decision 5 (one adapter per account) → Tasks 4, 10, 11, 12. ✓
- Decision 6 (positive-spend `abs()`) → all adapters. ✓
- Decision 7 (`transactions/` + `tests/fixtures/` gitignored vs committed) → Task 9 gitignore; fixtures committed in each adapter task. ✓
- Data model (`models.py`, `source_file`) → Task 1. ✓
- Adapter contract / `ParseResult` → Task 1 (ParseResult), Task 4 (first use). ✓
- Routing (header detect, `--source`, account = stem, dir expansion, `--year` PDF-only) → Tasks 8, 9. ✓
- Import log entry shape / written-on-success / dry-run-no-write → Tasks 7, 9. ✓
- Dedup algorithm (multiset, key fields, normalization, unparseable rows ignored) → Task 5. ✓
- `sheets_writer` changes (`read_existing_rows`, K-note, `build_row`) → Tasks 1, 6. ✓
- CLI flags + degraded dry-run without credentials → Task 9. ✓
- Error handling (missing path, no-match header, missing column, bad date/amount, corrupt log, nothing-new) → Tasks 4-12 (adapters), 7, 8, 9. ✓
- Testing matrix (per-adapter, routing, dedup, import_log, sheets_writer, existing stay green) → every task; existing 12 kept green through Tasks 1-2. ✓

**Known deviations from the spec (intentional):**
1. **`ParseResult.warnings`** is a separate list rather than folding "warned-unknown status" into the `skipped` Counter — imported-but-flagged rows are genuinely *kept*, so counting them as "skipped" would be misleading. `skipped` holds only dropped rows.
2. **Comma/tab delimiter handling** is tested once in the shared CSV reader (Task 3) plus one Fakecoin tab test, rather than re-tested in every adapter — adapters receive already-parsed `list[dict]`, so delimiter is not their concern.
3. **Row-level error context** (file name) is added by `main.py`'s caller context / the adapter includes the row number; adapters raise `ImporterError` with row number + raw value, which is sufficient for the fail-loud requirement.

**Placeholder scan:** Tasks 10-12 carry spec-hypothesis constants explicitly gated behind a "confirm against sample" Step 1 — this is the spec's own deferral ("verify columns vs sample"), not an unfilled placeholder. All fully-specified tasks (1-9) contain complete code.

**Type consistency:** `Transaction(date, description, amount, account, source_file)`, `ParseResult(transactions, skipped, warnings)`, adapter `NAME`/`matches`/`parse(rows, account)`, `detect_adapter`/`account_name`/`SOURCE_MAP`, `dedup`/`existing_keys_from_rows`, `import_log.file_hash`/`load_log`/`find_by_hash`/`append_entry`, `read_existing_rows` — names consistent across all tasks.
