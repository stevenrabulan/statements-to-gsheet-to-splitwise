# transactions/

Drop your **real account exports** here to import them. Everything in this folder
is **gitignored** except this README — real financial records are never committed.
(Synthetic test data lives separately under `tests/fixtures/`, committed and fake.)

## Layout: one folder per month

```
transactions/
  2026-06/
    Chase Sapphire Reserve.csv
    Chase Checking.csv
    Discover Card.csv
    Fakecoin Card.csv
  2026-07/
    ...
```

Import a whole month at once — a directory expands to all its `*.csv` and `*.pdf`:

```bash
python main.py transactions/2026-06/
python main.py transactions/2026-06/ --dry-run     # preview, writes nothing
```

## Filename = account name

**The file's name (without extension) becomes the account label in sheet column G.**
So name each file exactly how the account should appear:

| File | Column G |
|------|----------|
| `Chase Sapphire Reserve.csv` | Chase Sapphire Reserve |
| `Chase Checking.csv` | Chase Checking |
| `Discover Card.csv` | Discover Card |

This is also how the importer distinguishes multiple Chase cards that share the
same CSV header. Override for a single file with `--account "Some Name"`.

## Notes

- **Re-running is safe.** Files already imported (by content hash) are skipped, and
  row-level dedup against the sheet means re-exporting "all time" only ever adds new
  spending. Use `--force` to reprocess a file already in the import log.
- **Adapter** is auto-detected from the CSV header (Fakecoin / Chase credit / Chase
  checking / Discover); PDFs route to the PDF parser by extension. Override with
  `--source`.
- **First import:** consider `--from YYYY-MM-DD` to avoid backfilling all-time history.
