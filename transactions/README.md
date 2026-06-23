# transactions/

Drop your **real account exports** here to import them. Everything in this folder
is **gitignored** except this README — real financial records are never committed.
(Synthetic test data lives separately under `tests/fixtures/`, committed and fake.)

## Layout: one folder per month

```
transactions/
  2026-06/
    Chase1111_Activity20260416_20260515_20260623.CSV
    Chase8842_Activity20260416_20260515_20260623.CSV
    Discover_Activity20260416_20260515_20260623.CSV
    Fakecoin Card.csv
  2026-07/
    ...
```

Import a whole month at once — a directory expands to all its `*.csv` and `*.pdf`:

```bash
python main.py transactions/2026-06/
python main.py transactions/2026-06/ --dry-run     # preview, writes nothing
```

## Account name comes from `accounts.json`

You don't rename exports. Instead, `accounts.json` (project root, gitignored) maps a
**distinctive substring of the filename** to the account label shown in sheet column G:

```json
{
  "Chase1111": "Chase Sapphire Reserve",
  "Chase8842": "Chase Checking",
  "Discover":  "Discover Card",
  "Fakecoin":  "Fakecoin Card"
}
```

So `Chase1111_Activity20260416_20260515_20260623.CSV` → "Chase Sapphire Reserve"
(the `1111` is the account's last 4 digits, which is how multiple Chase cards sharing
one CSV format are told apart). Longest matching key wins. Copy `accounts.example.json`
to `accounts.json` and fill in your accounts. Override for one run with `--account "Name"`.

## Notes

- **Re-running is safe.** Files already imported (by content hash) are skipped, and
  row-level dedup against the sheet means re-exporting "all time" only ever adds new
  spending. Use `--force` to reprocess a file already in the import log.
- **Adapter** is auto-detected from the CSV header (Fakecoin / Chase credit / Chase
  checking / Discover); PDFs route to the PDF parser by extension. Override with
  `--source`.
- **First import:** consider `--from YYYY-MM-DD` to avoid backfilling all-time history.
