# 02: Tracer bullet: one simple Amazon Order becomes one Item row

**What to build:** Steven drops a scraped Amazon Order file into the month's transactions folder and runs the usual import. A single-Item Order with its own tax becomes one sheet row showing its Loaded Cost as a formula. Re-running the import writes nothing. This ticket fixes the scraped-file contract that every later ticket builds on. See the spec's "Scraped file contents", "Amazon adapter", "Row shape", "Deduplication", and "Configuration" sections.

**Blocked by:** None, can start immediately.

**Status:** ready-for-agent

- [ ] The scraped-file contract from the spec is captured as a synthetic JSON fixture with a schema version.
- [ ] The CLI's folder expansion picks up JSON files alongside CSVs and PDFs and routes them to a new Amazon adapter.
- [ ] The accounts config accepts an Amazon entry (a key matching the scraped filename, name "Amazon", and a Cutoff Date). The example config shows it.
- [ ] A single-Item Order with per-Item tax produces one row:
  - [ ] Order Date = the date the Order was placed
  - [ ] Item = the short name, with a quantity prefix when above 1 (e.g. "2× Glad ForceFlex Trash Bags")
  - [ ] Amount = a formula of rounded dollar amounts (quantity × price, then tax), omitting zero terms and the multiplier for quantity 1
  - [ ] Notes = `split-transactions automation amazon <order number> #<position>`
- [ ] Payment Method comes from the payment's last four digits matched against accounts-config keys. Gift card only gives "Amazon Gift Card", points only gives "Points", and a card plus gift card gives the card. An unmatched card falls back to the Amazon entry's name with a warning.
- [ ] Card rows are unchanged. The new optional Transaction fields (formula, key, Send to Splitwise, For who) are unset for them.
- [ ] Amazon rows are deduplicated by the key in Notes, not by date, amount, and description. Re-importing the same Order writes nothing, even if an amount differs by a cent.
- [ ] `--dry-run`, `--from`/`--to`, `--force`, and the import log behave as they do for card files.
- [ ] Tested at both seams: the adapter's parse (fixture in, rows out) and the CLI run with the sheet faked (rows checked after the row builder runs).
