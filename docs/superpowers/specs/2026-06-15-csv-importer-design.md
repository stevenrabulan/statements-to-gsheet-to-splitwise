# Multi-Account CSV Importer — Design Spec

- **Date:** 2026-06-15
- **Status:** Approved (design), pending implementation plan
- **Supersedes:** the single-issuer "Fakecoin CSV parser" direction; folds it in as the first adapter
- **Builds on:** `docs/superpowers/plans/2026-06-01-pdf-to-sheets.md` (the PDF tool, already shipped)

## Terminology

- **Account** — a specific source of transactions: a credit card *or* a bank/checking account. Its name (e.g. "Chase Sapphire Reserve", "Chase Checking") is written to sheet column G.
- **Source adapter** — the per-format parser for one account kind (`chase-credit`, `chase-checking`, `discover`, `fakecoin`, `pdf`). Each maps a raw export into the common `Transaction` model.
- **Spending** — money out: credit-card purchases and checking-account debits. This is what gets imported; money in (payments, deposits, credits, refunds) and internal transfers are excluded.

## Goal

Import **spending** from per-account CSV exports (Chase credit ×3–4, Chase checking, Discover, Fakecoin) into the Google Sheet that feeds Splitwise — **idempotently**, so re-running or over-broad exports never create duplicates. The existing PDF path is retained as a fallback adapter.

## Context & problem

The shipped tool computes one global billing window (16th→15th from today) and filters all transactions to it. That breaks once there are multiple accounts: each closes/cycles on a different date. Worse, CSV exports are *date ranges*, not statements — Fakecoin defaults to "all time"; Chase/Discover offer "since last statement" but also "YTD" / "last 24 months"; checking has its own ranges. So neither "one global window" nor "one file = one statement" reliably defines what to import.

## Key decisions (with rationale)

1. **CSV for every account; skip Excel; PDF retained as fallback.** Header-mapped CSV parsing is far more robust than PDF regex and keeps a future auto-fetch agent simple. Excel would add an `openpyxl`/`pandas` dependency for zero gain since CSV is always offered. PDF stays available where a CSV export isn't.
2. **Idempotent import via dedup against the sheet — replaces the billing-window filter.** The tool reads existing sheet rows and appends only transactions not already present. This makes the export's date range irrelevant to correctness: export "all time" every month and only new rows land. This is the keystone decision; everything else follows from it.
3. **File-level import log — skip already-processed files.** A content-hashed ledger records which files were imported; an unchanged file already in the log is skipped (override with `--force`). Complements row-level dedup: the log is *file* identity, dedup is *row* identity. (See Import log.)
4. **Optional explicit date range (`--from`/`--to`)** for when scoping *is* wanted (notably the very first import, to avoid backfilling all-time history into Splitwise). Default: no date filter — import all new (deduped) spending.
5. **One isolated adapter per account kind.** Each export has different columns *and* sign conventions, so each gets its own small, independently tested unit. Adding an account later = one new file + tests.
6. **Positive-spend convention.** Adapters normalize spending to positive amounts (matching the shipped PDF tool and the sheet). Accounts that report spending as negative (Chase credit purchases, checking debits) get `abs()`'d.
7. **Exported files live in `statements/<YYYY-MM>/`, gitignored.** Real financial records must never be committed. Year-month folders group each monthly batch and let the tool (and the future agent) import a whole month at once. Synthetic test fixtures live separately under `tests/fixtures/` (committed, fake).
8. **Phasing.** Phase 1 (this spec) = the manual import tool. Phase 2 (separate spec, later) = an agent that logs into each portal and downloads exports into `statements/<YYYY-MM>/`, then runs Phase 1. Bank logins + MFA make it its own design.

## Architecture

```
split-transactions/
├── main.py              # CLI · routing · import-log + dedup orchestration
├── models.py            # Transaction dataclass (moved out of pdf_parser)
├── adapters/
│   ├── __init__.py      # registry + detect_adapter(header) → adapter
│   ├── fakecoin.py       # Fakecoin credit CSV  (format known)
│   ├── chase_credit.py   # Chase credit CSV     (verify columns vs sample)
│   ├── chase_checking.py # Chase checking CSV   (verify columns + filtering vs sample)
│   ├── discover.py       # Discover credit CSV  (verify columns vs sample)
│   └── chase_pdf.py     # existing PDF parser, relocated (fallback)
├── dedup.py             # multiset key-matching (row identity)
├── import_log.py        # read/append the file ledger
├── date_filter.py       # retained for optional --from/--to (in_window reused)
├── sheets_writer.py     # + read_existing_rows(); append unchanged
├── import_log.json      # gitignored file ledger (runtime state)
├── statements/<YYYY-MM>/  # gitignored real exports
└── tests/ (+ fixtures/)
```

### Data flow
```
main.py <path…>                       # files and/or directories
  → expand directories to *.csv (+ *.pdf)
  → per file: skip if its hash is already in import_log.json (unless --force)
  → detect adapter (CSV header) or --source → adapter → list[Transaction]
    (each stamped with the file basename for the column-K note)
  → optional --from/--to filter (date_filter.in_window)
  → dedup against current sheet rows
  → dry-run preview  →  append only the new rows  →  record file in import log
```

## Data model

```python
@dataclass
class Transaction:
    date: date          # transaction date
    description: str     # merchant / payee
    amount: float        # positive spend, rounded to cents at write
    account: str         # column G label (card or bank account name)
    source_file: str     # import file basename — used for the column-K note
```
`Transaction` moves from `pdf_parser.py` to `models.py`; `sheets_writer` and all adapters import it from there.

## Adapter contract

Each adapter exposes:
```python
NAME: str                       # "chase-credit" | "chase-checking" | "discover" | "fakecoin" | "pdf"
def matches(header: list[str]) -> bool          # header-sniff for routing
def parse(rows: list[dict], account: str) -> ParseResult
```
`ParseResult` carries `transactions: list[Transaction]` plus a `skipped` summary (counts grouped by reason: payment/deposit, credit/refund, transfer, dead status, warned-unknown status). Adapter rules:
- Keep **spending only** (purchases / debits); drop money-in (payments, deposits, credits, refunds) and internal transfers per the account's signal.
- Normalize amount to **positive** spend.
- Parse the account's date format to a `date`.
- Map merchant/payee → description; strip whitespace.

### Per-account mapping

**Fakecoin credit** (confirmed format) — tab/comma-delimited, header:
`Date, Amount, Currency, Type, Status, Merchant, Card Last Four, Reward Amount, Reward Currency, Reward Status, Reward Rate`
- Keep `Type == PURCHASE`. Drop `PAYMENT` and any other type.
- Status: skip denylist `{DECLINED, REVERSED, CANCELED, CANCELLED, FAILED}`; import known-good `{AUTHORIZED, SETTLED, CLEARED}`; **import-but-warn** on any other status.
- `Date` is ISO `YYYY-MM-DD`; `Amount` positive already; `Merchant` → description.

**Chase credit** (expected standard format — verify against sample) — header:
`Transaction Date, Post Date, Description, Category, Type, Amount, Memo`
- Keep `Type == Sale`; drop `Payment`, `Return`, `Fee`, `Adjustment`.
- `Amount` is **negative for purchases** → `abs()`. Date `MM/DD/YYYY` → `date`.

**Chase checking** (expected standard format — verify columns *and* filtering against sample) — header:
`Details, Posting Date, Description, Amount, Type, Balance, Check or Slip #`
- Keep **debits** (`Details == DEBIT`, negative `Amount`) → `abs()` to positive spend.
- **Exclude** credits/deposits (`Details == CREDIT`), **internal transfers**, and **credit-card payments** — otherwise spending already imported from a card is double-counted as the checking-account payment to that card. Identified via `Type` (e.g. `ACCT_XFER`, loan/card-payment types) and description patterns; the exact rules are confirmed against a sample.
- `Posting Date` `MM/DD/YYYY` → date; `Description` → description.

**Discover credit** (expected standard format — verify against sample) — header:
`Trans. Date, Post Date, Description, Amount, Category`
- Purchases have **positive** `Amount`; drop rows with negative amount or `Category == "Payments and Credits"`.
- Date `MM/DD/YYYY` → `date`.

Exact header strings and (for checking) the transfer/payment exclusions are verified against a real sample during implementation; each adapter's TDD fixture is the source of truth.

## Routing

- **Adapter:** for `.csv`, auto-detected by matching the header against each adapter's `matches()` (the reader sniffs comma vs tab first); no match → loud error listing supported accounts + the unrecognized header. `.pdf` routes to the `pdf` adapter by extension. `--source` overrides either. (Chase credit vs Chase checking are distinguished by their distinct headers.)
- **Account name (column G):** the **filename stem** by default — e.g. `Chase Sapphire Reserve.csv` → "Chase Sapphire Reserve", `Chase Checking.csv` → "Chase Checking". This distinguishes accounts that share a header (3–4 Chase cards) and is the naming convention the future agent follows. `--account` overrides (single-file use).
- **Inputs:** any mix of files and directories. A directory expands to its `*.csv` (and `*.pdf`). This enables `main.py statements/2026-06/` to import a whole month.
- `--year` applies to the PDF adapter only (PDF dates are `MM/DD`); all CSV dates are complete.

## Import log

- **File:** `import_log.json` at project root, **gitignored** (runtime state referencing your account filenames — not committed).
- **Per-file entry:** `{ "file": "<relative path>", "sha256": "<hash of bytes>", "account": "<column-G label>", "source": "<adapter NAME>", "imported_at": "<ISO 8601>", "rows_new": <int>, "rows_skipped": <int>, "date_range": ["<min ISO>", "<max ISO>"] }`.
- **Skip-if-seen (default):** before processing, the file's SHA-256 is computed; if an entry with that hash exists, the file is **skipped** with a note (`already imported <date>`). `--force` reprocesses it (row-level dedup still prevents duplicate rows). Hashing *content* (not name) means a re-export containing new transactions is treated as new and processed, while an identical re-run is skipped.
- **Written only on success:** the entry is appended after the sheet append succeeds, so a failed run can be retried. `--dry-run` reads the log (to show would-skip / would-import) but never writes it.
- `import_log.py` owns read/append with validation: a missing or corrupt log starts fresh with a warning rather than crashing.

## Dedup

1. Read existing sheet rows (cols A,B,C,G) via `sheets_writer.read_existing_rows()`.
2. Build a **multiset** (`collections.Counter`) of keys:
   `(date, round(amount, 2), normalized_description, normalized_account)` where
   `normalized_description = " ".join(description.upper().split())` and
   `normalized_account = account.strip().upper()`.
   The source filename / column-K note is deliberately **not** part of the key, so the same charge re-exported under a different filename still dedups.
   Rows that don't parse (headers, Amazon formula rows, blanks) are skipped — they simply won't match incoming keys.
3. For each incoming transaction in order: if its key still has remaining count in the existing multiset, **consume one and skip** (already in the sheet); otherwise **keep it**. The tool does *not* count its own writes — so a genuine repeat charge (two identical $5 coffees, none yet in the sheet) is preserved, while re-importing the same export adds nothing.

This is best-effort: a manually-entered row spelled differently won't match (could yield a duplicate). The dry-run preview is the human check before writing.

## sheets_writer changes

- Add `read_existing_rows() -> list[list]` — reads the tab's `A:K` (defensive parse: dates as `MM/DD/YYYY`, amounts stripped of `$`/commas; unparseable rows ignored by dedup).
- `append_transactions()` unchanged (still `USER_ENTERED`, `INSERT_ROWS`).
- `build_row` layout A=date, B=amount, C=desc, E=✓, G=account, **K = provenance note** `split-transactions automation <source_file>` (e.g. `split-transactions automation Chase Sapphire Reserve.csv`, using the file's real basename incl. extension) — replaces the old constant `"Automated by Claude"`. Falls back to `split-transactions automation` if `source_file` is empty.

## CLI

```
python main.py <path…> [--account NAME] [--source chase-credit|chase-checking|discover|fakecoin|pdf]
                       [--from YYYY-MM-DD] [--to YYYY-MM-DD] [--year YYYY] [--force] [--dry-run]
```
- `--dry-run` reads the sheet (read-only) and previews exactly what *would* be appended after dedup; writes nothing (and doesn't touch the import log). If `credentials.json` is absent it degrades: prints parsed+filtered rows and warns that **dedup was skipped**, so parsing can still be sanity-checked without credentials.
- `--force` reprocesses files already in the import log.
- Run prints, per file: skipped-as-already-imported *or* (adapter detected, account name, counts: parsed / kept / skipped-by-reason / new-after-dedup), then the preview table.

## Error handling (fail loud)

- Path missing (file or directory) → clear message (also closes the current PDF traceback gap).
- CSV header matches no adapter → error listing supported accounts + the unrecognized header.
- Expected column missing for the detected adapter → error naming the column.
- Unparseable date/amount in a row → error with file name + row number + raw content; never silently dropped.
- Corrupt `import_log.json` → warn and start fresh, never crash.
- Empty file / nothing left after filtering+dedup → "nothing new to write" (clean exit).

## Testing (TDD)

- **Per adapter** (`tests/test_adapter_<name>.py`) with a committed synthetic fixture under `tests/fixtures/`:
  - correct field mapping (date parse, payee→description, amount sign normalized to positive);
  - money-in excluded (payments / deposits / credits / refunds), and for checking: transfers + card-payments excluded;
  - Fakecoin: dead status excluded, unknown status imported-with-warning;
  - both comma- and tab-delimited input parse;
  - missing expected column raises.
- **`tests/test_routing.py`:** header → correct adapter (incl. Chase credit vs checking); unrecognized header raises; filename stem → account name.
- **`tests/test_dedup.py`:** exact re-import adds nothing; true repeat charge preserved; partial overlap (sheet has 1, batch has 2 → add 1); unparseable existing rows ignored.
- **`tests/test_import_log.py`:** unchanged file skipped; `--force` reprocesses; re-export with new content processed; corrupt log → fresh start; log written only on success (not in dry-run).
- **`tests/test_sheets_writer.py`:** `build_row` writes K = `split-transactions automation <source_file>` (and falls back to `split-transactions automation` when empty); `Transaction` gains `source_file`.
- Existing `date_filter` / `pdf_parser` tests stay green (the `pdf_parser`→`chase_pdf` + `models.py` move updates imports only; the K-note + `source_file` field update `test_sheets_writer`).

## Out of scope (Phase 1)

- **Phase 2 auto-fetch agent** (Chrome-extension portal login + download) — separate spec.
- **Excel (`.xlsx`) ingestion** — CSV is always available.
- **Fuzzy / description-normalized dedup** beyond uppercase+whitespace — revisit only if false duplicates show up in practice.
- **Per-account statement-cycle config** — dedup makes it unnecessary.

## Implementation inputs still needed

- A real **Chase credit CSV**, **Chase checking CSV**, and **Discover CSV** sample (header + 2–3 rows; redact values) to finalize those adapters' column maps and sign conventions. The Fakecoin adapter is fully specified.
- For **Chase checking specifically:** confirm which debits count as shared spending and how transfers / credit-card payments appear (so they can be excluded). The sample plus a one-line rule from you settles it.
- These can arrive at implementation time; each adapter is an independent task.
