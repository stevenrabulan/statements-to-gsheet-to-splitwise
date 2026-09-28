# 02: Tracer bullet: one simple Amazon Order becomes one Item row

**What to build:** Steven drops a scraped Amazon Order file into the month's transactions folder and runs the usual import. A single-Item Order with its own tax becomes one sheet row showing its Loaded Cost as a formula. Re-running the import writes nothing. This ticket fixes the scraped-file contract that every later ticket builds on. See the spec's "Scraped file contents", "Amazon adapter", "Row shape", "Deduplication", and "Configuration" sections.

**Blocked by:** None, can start immediately.

**Status:** done

- [x] The scraped-file contract from the spec is captured as a synthetic JSON fixture with a schema version.
- [x] The CLI's folder expansion picks up JSON files alongside CSVs and PDFs and routes them to a new Amazon adapter.
- [x] The accounts config accepts an Amazon entry (a key matching the scraped filename, name "Amazon", and a Cutoff Date). The example config shows it.
- [x] A single-Item Order with per-Item tax produces one row:
  - [x] Order Date = the date the Order was placed
  - [x] Item = the short name, with a quantity prefix when above 1 (e.g. "2× Glad ForceFlex Trash Bags")
  - [x] Amount = a formula of rounded dollar amounts (quantity × price, then tax), omitting zero terms and the multiplier for quantity 1
  - [x] Notes = `split-transactions automation amazon <order number> #<position>`
- [x] Payment Method comes from the payment's last four digits matched against accounts-config keys. Gift card only gives "Amazon Gift Card", points only gives "Points", and a card plus gift card gives the card. An unmatched card falls back to the Amazon entry's name with a warning.
- [x] Card rows are unchanged. The new optional Transaction fields (formula, key, Send to Splitwise, For who) are unset for them.
- [x] Amazon rows are deduplicated by the key in Notes, not by date, amount, and description. Re-importing the same Order writes nothing, even if an amount differs by a cent.
- [x] `--dry-run`, `--from`/`--to`, `--force`, and the import log behave as they do for card files.
- [x] Tested at both seams: the adapter's parse (fixture in, rows out) and the CLI run with the sheet faked (rows checked after the row builder runs).

## Comments

**Implemented (2026-09-28).** Notes for later tickets:

- The full schema-version-1 contract is now in the spec under "Scraped file contents". Promos are per Order with target `positions`, not per Item.
- Until 03 lands, an Order with Promos, shipping, discounts, or tax only on the shipment is skipped as "needs cost allocation" (with a warning) rather than written wrong. Ticket 03 should remove that guard in `adapters/amazon.py`.
- The Amazon entry reuses `ignore_before` as its Cutoff Date. The CLI's generic cutoff still compares Order Date for Amazon rows, and cancelled or unshipped Items are still written. Ticket 04 owns both.
- If an Order is paid by gift card plus points with no card, the Payment Method falls back to the Amazon entry's name with a warning. The spec doesn't cover this case.
- The key format lives in `adapters/amazon.py` (`item_key`, `KEY_PATTERN`). `KEY_PATTERN` already recognizes Refund keys, so an Item key never matches a Refund row.
