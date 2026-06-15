# Multi-Issuer CSV Importer — Design Spec

- **Date:** 2026-06-15
- **Status:** Approved (design), pending implementation plan
- **Supersedes:** the single-issuer "Fakecoin CSV parser" direction; folds it in as the first adapter
- **Builds on:** `docs/superpowers/plans/2026-06-01-pdf-to-sheets.md` (the PDF tool, already shipped)

## Goal

Import credit-card **purchases** from per-issuer CSV exports (Chase ×3–4, Discover, Fakecoin) into the Google Sheet that feeds Splitwise — **idempotently**, so re-running or over-broad exports never create duplicates. The existing PDF path is retained as a fallback adapter.

## Context & problem

The shipped tool computes one global billing window (16th→15th from today) and filters all transactions to it. That breaks once there are multiple cards: each closes on a different date. Worse, CSV exports are *date ranges*, not statements — Fakecoin defaults to "all time"; Chase/Discover offer "since last statement" but also "YTD" / "last 24 months". So neither "one global window" nor "one file = one statement" reliably defines what to import.

## Key decisions (with rationale)

1. **CSV for every issuer; skip Excel; PDF retained as fallback.** Header-mapped CSV parsing is far more robust than PDF regex and keeps a future auto-fetch agent simple. Excel would add an `openpyxl`/`pandas` dependency for zero gain since CSV is always offered. PDF stays available where a CSV export isn't.
2. **Idempotent import via dedup against the sheet — replaces the billing-window filter.** The tool reads existing sheet rows and appends only transactions not already present. This makes the export's date range irrelevant to correctness: export "all time" every month and only new rows land. This is the keystone decision; everything else follows from it.
3. **Optional explicit date range (`--from`/`--to`)** for when scoping *is* wanted (notably the very first import, to avoid backfilling all-time history into Splitwise). Default: no date filter — import all new (deduped) purchases.
4. **One isolated adapter per issuer.** Each issuer's CSV has different columns *and* sign conventions, so each gets its own small, independently tested unit. Adding a card later = one new file + tests.
5. **Positive-spend convention.** Adapters normalize purchases to positive amounts (matching the shipped PDF tool and the sheet). Issuers that report purchases as negative (Chase) get `abs()`'d.
6. **Exported files live in `statements/<YYYY-MM>/`, gitignored.** Real financial records must never be committed. Year-month folders group each monthly batch and let the tool (and the future agent) import a whole month at once. Synthetic test fixtures live separately under `tests/fixtures/` (committed, fake).
7. **Phasing.** Phase 1 (this spec) = the manual import tool. Phase 2 (separate spec, later) = an agent that logs into each portal and downloads exports into `statements/<YYYY-MM>/`, then runs Phase 1. Bank logins + MFA make it its own design.

## Architecture

```
split-transactions/
├── main.py              # CLI · routing · dedup orchestration
├── models.py            # Transaction dataclass (moved out of pdf_parser)
├── adapters/
│   ├── __init__.py      # registry + detect_issuer(header) → adapter
│   ├── fakecoin.py      # Fakecoin CSV  (format known)
│   ├── chase.py         # Chase CSV     (verify columns vs sample)
│   ├── discover.py      # Discover CSV  (verify columns vs sample)
│   └── chase_pdf.py     # existing PDF parser, relocated (fallback)
├── dedup.py             # multiset key-matching
├── date_filter.py       # retained for optional --from/--to (in_window reused)
├── sheets_writer.py     # + read_existing_rows(); append unchanged
├── statements/<YYYY-MM>/  # gitignored real exports
└── tests/ (+ fixtures/)
```

### Data flow
```
main.py <path…>                       # files and/or directories
  → expand directories to *.csv (+ *.pdf)
  → per file: detect issuer (CSV header) or --issuer → adapter → list[Transaction]
  → optional --from/--to filter (date_filter.in_window)
  → dedup against current sheet rows
  → dry-run preview  →  append only the new rows
```

## Data model

```python
@dataclass
class Transaction:
    date: date          # transaction date
    description: str     # merchant
    amount: float        # positive spend, rounded to cents at write
    card_name: str       # column G label
```
`Transaction` moves from `pdf_parser.py` to `models.py`; `sheets_writer` and all adapters import it from there.

## Adapter contract

Each adapter exposes:
```python
ISSUER: str                       # "chase" | "discover" | "fakecoin"
def matches(header: list[str]) -> bool          # header-sniff for routing
def parse(rows: list[dict], card_name: str) -> ParseResult
```
`ParseResult` carries `transactions: list[Transaction]` plus a `skipped` summary (counts grouped by reason: payment, credit/refund, dead status, warned-unknown status). Adapter rules:
- Keep purchases only; drop payments/credits/refunds per the issuer's signal.
- Normalize amount to **positive** spend.
- Parse the issuer's date format to a `date`.
- Map merchant/description; strip whitespace.

### Per-issuer mapping

**Fakecoin** (confirmed format) — tab/comma-delimited, header:
`Date, Amount, Currency, Type, Status, Merchant, Card Last Four, Reward Amount, Reward Currency, Reward Status, Reward Rate`
- Keep `Type == PURCHASE`. Drop `PAYMENT` and any other type.
- Status: skip denylist `{DECLINED, REVERSED, CANCELED, CANCELLED, FAILED}`; import known-good `{AUTHORIZED, SETTLED, CLEARED}`; **import-but-warn** on any other status.
- `Date` is ISO `YYYY-MM-DD`; `Amount` positive already; `Merchant` → description.

**Chase** (expected standard format — verify against sample) — header:
`Transaction Date, Post Date, Description, Category, Type, Amount, Memo`
- Keep `Type == Sale`; drop `Payment`, `Return`, `Fee`, `Adjustment`.
- `Amount` is **negative for purchases** → `abs()`. Date `MM/DD/YYYY` → `date`.

**Discover** (expected standard format — verify against sample) — header:
`Trans. Date, Post Date, Description, Amount, Category`
- Purchases have **positive** `Amount`; drop rows with negative amount or `Category == "Payments and Credits"`.
- Date `MM/DD/YYYY` → `date`.

The exact header strings for Chase/Discover are verified against a real sample during implementation; the TDD fixture for each adapter is the source of truth.

## Routing

- **Issuer:** for `.csv`, auto-detected by matching the header against each adapter's `matches()` (the reader sniffs comma vs tab first); no match → loud error listing supported issuers. `.pdf` routes to the `chase_pdf` adapter by extension. `--issuer` overrides either.
- **Card name (column G):** the **filename stem** by default — e.g. `Chase Sapphire Reserve.csv` → "Chase Sapphire Reserve". This distinguishes 3–4 Chase cards (identical headers) and is the naming convention the future agent follows. `--card` overrides (single-file use).
- **Inputs:** any mix of files and directories. A directory expands to its `*.csv` (and `*.pdf`). This enables `main.py statements/2026-06/` to import a whole month.
- `--year` applies to the PDF adapter only (PDF dates are `MM/DD`); CSV dates are complete.

## Dedup

1. Read existing sheet rows (cols A,B,C,G) via `sheets_writer.read_existing_rows()`.
2. Build a **multiset** (`collections.Counter`) of keys:
   `(date, round(amount, 2), normalized_merchant, normalized_card)` where
   `normalized_merchant = " ".join(description.upper().split())` and
   `normalized_card = card_name.strip().upper()`.
   Rows that don't parse (headers, Amazon formula rows, blanks) are skipped — they simply won't match incoming keys.
3. For each incoming transaction in order: if its key still has remaining count in the existing multiset, **consume one and skip** (already in the sheet); otherwise **keep it**. The tool does *not* count its own writes — so a genuine repeat charge (two identical $5 coffees, none yet in the sheet) is preserved, while re-importing the same export adds nothing.

This is best-effort: a manually-entered row spelled differently won't match (could yield a duplicate). The dry-run preview is the human check before writing.

## sheets_writer changes

- Add `read_existing_rows() -> list[list]` — reads the tab's `A:K` (defensive parse: dates as `MM/DD/YYYY`, amounts stripped of `$`/commas; unparseable rows ignored by dedup).
- `append_transactions()` unchanged (still `USER_ENTERED`, `INSERT_ROWS`, `build_row` layout A=date,B=amount,C=desc,E=✓,G=card,K="Automated by Claude").

## CLI

```
python main.py <path…> [--card NAME] [--issuer chase|discover|fakecoin|chase-pdf]
                       [--from YYYY-MM-DD] [--to YYYY-MM-DD] [--year YYYY] [--dry-run]
```
- `--dry-run` reads the sheet (read-only) and previews exactly what *would* be appended after dedup; writes nothing. If `credentials.json` is absent it degrades: prints parsed+filtered rows and warns that **dedup was skipped**, so parsing can still be sanity-checked without credentials.
- Run prints, per file: issuer detected, card name, counts (parsed / kept / skipped-by-reason / new-after-dedup), then the preview table.

## Error handling (fail loud)

- Path missing (file or directory) → clear message (also closes the current PDF traceback gap).
- CSV header matches no adapter → error listing supported issuers + the unrecognized header.
- Expected column missing for the detected issuer → error naming the column.
- Unparseable date/amount in a row → error with file name + row number + raw content; never silently dropped.
- Empty file / nothing left after filtering+dedup → "nothing new to write" (clean exit).

## Testing (TDD)

- **Per adapter** (`tests/test_adapter_<issuer>.py`) with a committed synthetic fixture under `tests/fixtures/`:
  - correct field mapping (date parse, merchant→description, amount sign normalized to positive);
  - payments/credits/refunds excluded;
  - Fakecoin: dead status excluded, unknown status imported-with-warning;
  - both comma- and tab-delimited input parse;
  - missing expected column raises.
- **`tests/test_routing.py`:** header → correct adapter; unrecognized header raises; filename stem → card name.
- **`tests/test_dedup.py`:** exact re-import adds nothing; true repeat charge preserved; partial overlap (sheet has 1, batch has 2 → add 1); unparseable existing rows ignored.
- Existing 12 tests stay green (the `pdf_parser`→`chase_pdf` + `models.py` move updates imports only).

## Out of scope (Phase 1)

- **Phase 2 auto-fetch agent** (Chrome-extension portal login + download) — separate spec.
- **Excel (`.xlsx`) ingestion** — CSV is always available.
- **Fuzzy / merchant-normalized dedup** beyond uppercase+whitespace — revisit only if false duplicates show up in practice.
- **Per-card statement-cycle config** — dedup makes it unnecessary.

## Implementation inputs still needed

- A real **Chase CSV** and **Discover CSV** sample (header + 2–3 rows) to finalize those two adapters' column maps and confirm sign conventions. The Fakecoin adapter is fully specified. These can arrive at implementation time; each adapter is an independent task.
