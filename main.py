#!/usr/bin/env python3
"""Multi-account CSV (+ PDF fallback) importer for the Splitwise sheet.

Usage:
    python main.py transactions/2026-06/                     # whole month
    python main.py "Fakecoin Card.csv"
    python main.py statement.pdf --source pdf --account "Chase Sapphire" --year 2026
    python main.py *.csv --dry-run
"""
import argparse
import sys
from datetime import date, datetime
from pathlib import Path

import accounts
import import_log
from adapters import detect_adapter, SOURCE_MAP
from models import ImporterError
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
            entries = [c for c in sorted(p.iterdir()) if c.is_file()]
            files.extend(c for c in entries if c.suffix.lower() == ".csv")
            files.extend(c for c in entries if c.suffix.lower() == ".pdf")
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


def _adapter_and_transactions(path: Path, args, mapping):
    """Route a single file and return (adapter_name, account, transactions, skipped, warnings)."""
    account = args.account or accounts.account_for_filename(path.name, mapping)
    if not account:
        raise ImporterError(
            f"{path.name}: no --account given and no accounts.json key matches its name. "
            f"Add an entry to accounts.json (see accounts.example.json)."
        )
    if args.source:
        adapter = SOURCE_MAP[args.source]
    elif path.suffix.lower() == ".pdf":
        adapter = SOURCE_MAP["pdf"]
    else:
        header, _rows = read_csv(path)
        adapter = detect_adapter(header)

    if adapter.NAME == "pdf":
        txns = adapter.parse_pdf(path, card_name=account, year=args.year)
        skipped, warnings = {}, []
    else:
        header, rows = read_csv(path)
        result = adapter.parse(rows, account=account)
        txns, skipped, warnings = result.transactions, result.skipped, result.warnings

    for t in txns:
        t.source_file = f"{path.parent.name}/{path.name}"
    return adapter.NAME, account, txns, skipped, warnings


def run(args) -> None:
    files = gather_files(args.paths)
    mapping = accounts.load_accounts(accounts.ACCOUNTS_PATH)
    date_from = _parse_date_arg(args.date_from, "from")
    date_to = _parse_date_arg(args.date_to, "to")

    log_path = import_log.LOG_PATH
    log = import_log.load_log(log_path)
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

        try:
            name, account, txns, skipped, warnings = _adapter_and_transactions(path, args, mapping)
        except ImporterError as exc:
            sys.exit(f"ERROR in {path.name}: {exc}")
        if date_from or date_to:
            lo = date_from or date.min
            hi = date_to or date.max
            txns = [t for t in txns if in_window(t.date, lo, hi)]

        new = dedup(txns, existing) if can_dedup and not args.force else txns
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

    last_end_row = max((entry.get("end_row", 1) for entry in log), default=1)
    start_search_row = max(1, last_end_row - 200)
    written, start_row, end_row = append_transactions(to_append, start_search_row)
    print(f"\nWrote {written} rows to the sheet (rows {start_row}-{end_row}).")
    for entry in pending_log_entries:                        # record only on success
        entry["imported_at"] = datetime.now().isoformat()
        if written > 0:
            entry["start_row"] = start_row
            entry["end_row"] = end_row
        import_log.append_entry(entry, log_path)


def main():
    run(parse_args())


if __name__ == "__main__":
    main()
