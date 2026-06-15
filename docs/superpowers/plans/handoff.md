# Session Handoff — PDF Transactions → Google Sheets

## What was built

A Python CLI tool that parses credit card statement PDFs and appends one row per transaction to a Google Sheet (the same sheet that feeds Splitwise).

## Repo

`/path/to/split-transactions/`

Git is NOT initialized yet — do that first:
```bash
cd ~/repos/sr/split-transactions
git init
git config user.email "steven.rabulan@gmail.com"
git config user.name "Steven"
git add .
git commit -m "chore: initial implementation — pdf to sheets workflow"
```

## Files created

```
split-transactions/
├── main.py                   # CLI entry point
├── pdf_parser.py             # Extracts transactions from PDF using pdfplumber
├── date_filter.py            # Billing window: 16th of last month → 15th of this month
├── sheets_writer.py          # Appends rows to Google Sheet via Sheets API
├── requirements.txt
├── .gitignore
├── tests/
│   ├── test_date_filter.py   # 5 tests ✅
│   ├── test_pdf_parser.py    # 5 tests ✅
│   └── test_sheets_writer.py # 2 tests ✅
└── docs/superpowers/plans/
    └── 2026-06-01-pdf-to-sheets.md   # Full implementation plan
```

All 12 tests pass: `python -m pytest tests/ -v`

## Google Sheet

- URL: https://docs.google.com/spreadsheets/d/YOUR_SPREADSHEET_ID/edit?gid=0
- Spreadsheet ID: `YOUR_SPREADSHEET_ID`
- Sheet GID: `0` (tab name resolved at runtime via API)
- Column layout: A=date, B=amount, C=description, E=checkbox, G=card name, K="Automated by Claude"

This matches the existing `log-amazon-transactions.md` convention.

## Usage

```bash
# Install deps (first time)
pip install -r requirements.txt

# Dry run — see what would be written
python main.py statement.pdf --card "Chase Sapphire" --dry-run

# Write to sheet
python main.py statement.pdf --card "Chase Sapphire"

# Cross-year Dec→Jan window
python main.py statement.pdf --card "Chase Sapphire" --year 2025
```

## What still needs to be done before first real run

### 1. Google Cloud credentials (required)
1. Go to https://console.cloud.google.com → create a project
2. Enable **Google Sheets API**
3. APIs & Services → Credentials → Create → OAuth 2.0 Client ID → **Desktop app**
4. Download as `credentials.json` into the project root
5. First run opens a browser for OAuth; `token.json` is created and reused after that

### 2. Adapt the PDF regex (likely required)
The regex in `pdf_parser.py` (`_TXN_PATTERN`) is tuned for Chase-style statements with 2+ space separation between columns. Run this first to see what your PDF actually looks like:

```bash
python3 -c "
import pdfplumber, sys
with pdfplumber.open(sys.argv[1]) as pdf:
    for i, page in enumerate(pdf.pages[:3]):
        print(f'=== PAGE {i+1} ===')
        print(page.extract_text())
" your-statement.pdf
```

Then update `_TXN_PATTERN` in `pdf_parser.py` to match your card's format. The plan at `docs/superpowers/plans/2026-06-01-pdf-to-sheets.md` (Task 3, Step 6) has a table of common variations and how to adapt.

## Key design decisions

- **One row per transaction** (unlike `log-amazon-transactions.md` which combines Amazon orders into one formula row)
- **Payments excluded** via `_SKIP_KEYWORDS` in `pdf_parser.py` — add keywords there if your card uses different language
- **Year rollover handled** — Dec→Jan billing windows correctly assign Jan transactions to the next year
- **Dry run flag** (`--dry-run`) prints rows without writing — always use this first

## Related file

`log-amazon-transactions.md` — the existing Amazon workflow (manual, screenshot-based, combines into one row). The new tool is the PDF equivalent but row-per-transaction.
