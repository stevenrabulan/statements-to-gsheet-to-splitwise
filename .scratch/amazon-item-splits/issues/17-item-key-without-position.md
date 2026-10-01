# 17: Item key that does not depend on Amazon's Item order

**What to build:** A key for an Item row that stays the same on every scrape. Today the key is `amazon <order number> #<position>`, and the position is the Item's place on Amazon's order details page. The first real run (ticket 15) showed that Amazon changes that order between page loads, so the position is not stable.

**Blocked by:** none

**Status:** needs-triage

## What the first real run found (2026-10-01)

The order details page of 14 Orders with more than one Item was loaded 3 times each, a few seconds apart. 4 of the 14 listed their Items in a different order between loads:

- `111-0000000-0000101`: the first two Items swapped.
- `111-0000000-0000102`: the second and third Items swapped.
- `111-0000000-0000103` (cancelled): the second and third Items swapped.
- `111-0000000-0000104`: the third and fourth Items swapped.

The invoice page of `111-0000000-0000104` also listed its two returned Items in the opposite order from the details page. The Orders list page uses a third order (for `111-0000000-0000105` it lists the second shipment first).

Every swap seen was inside one shipment box. No Item moved to another shipment.

## Why it matters

- **A Refund can land on the wrong Item.** A Refund names positions. If a later scrape numbers the Items differently, the negative row copies "For who" and "Send to Splitwise" from another Item's row.
- **A re-scrape can skip or duplicate an Item** when an Order's Items import on different runs (one shipment ships later than another), because the later run may give an already-imported position to a different Item.
- Rows from one run are still right: each formula is calculated from the Item it describes, and the Order's rows sum to the Order Total.

## To decide

What identifies an Item inside an Order. Options seen on the page:

- **ASIN** (in each Item's product link). Stable, and unique inside an Order as far as this scrape shows, because Amazon merges the same product into one line with a quantity. Needs a new field in the scrape file and a schema version bump.
- **Full title.** No new page reading, but long, and two variants can share a title prefix.
- **Position after sorting** by a stable field (ASIN or title). Keeps `#<position>` in the key, but the number changes when an Item is added to the list.

## Notes for whoever picks this up

- No Item rows are in the sheet yet (the ticket 15 import has not run), so no existing keys need migrating if this lands first.
- The scrape prompt (`scrape-amazon-orders.md`, "Item" field rules) tells the scraper to count positions "the same way every time". That instruction cannot be followed, since the page itself reorders.
- Tests for the key live in `tests/test_adapter_amazon.py` and `tests/test_dedup.py`.

## Comments

- 2026-10-01: Opened from ticket 15, whose last step says to open this ticket if positions differ between scrapes.
