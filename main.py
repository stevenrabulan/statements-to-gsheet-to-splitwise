#!/usr/bin/env python3
"""
Usage:
    python main.py statement.pdf --card "Chase Sapphire" --year 2026
    python main.py *.pdf --card "Chase Sapphire"
"""
import argparse
from datetime import date

from date_filter import billing_window, in_window
from adapters.chase_pdf import parse_pdf
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
        txns = parse_pdf(pdf_path, card_name=args.card, year=args.year, billing_start=start)
        if not txns:
            print(f"  WARNING: No transactions found in {pdf_path}. "
                  "The PDF format may not match the expected pattern. "
                  "See pdf_parser.py to adapt the regex.")
        in_range = [t for t in txns if in_window(t.date, start, end)]
        print(f"  Found {len(txns)} transactions, {len(in_range)} in window")
        all_transactions.extend(in_range)

    if not all_transactions:
        print("No transactions to write.")
        return

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
