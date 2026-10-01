# 14: Scrape prompt version 2 and docs

**What to build:** The scrape prompt produces schema version 2 files that match what Amazon really shows, and the README describes the new workflow. See the spec addendum.

**Blocked by:** 08, 09, 10, 11, 12, 13

**Status:** ready-for-agent

- [ ] `scrape-amazon-orders.md` writes `schema_version` 2 with `kind` on every Order.
- [ ] Order Total is the total before gift card or points, with the Amazon line named.
- [ ] Tax goes on the Order when Amazon shows it once, and on the shipment when shown per shipment.
- [ ] Ship date is the "Package left the shipper facility" date, `null` when tracking is gone.
- [ ] A coupon with no visible targets is recorded with `positions: []`.
- [ ] Refunds list `positions`, including one Refund that covers several Items.
- [ ] Whole Foods Orders are found by walking the Orders list (not the search box) and recorded with `charges`, `discounts`, `delivered`, and the Order Total.
- [ ] The Digital Orders tab is read, with the card taken from each details page.
- [ ] Only Steven's own account is read, never another account's Orders.
- [ ] The README covers Whole Foods and Digital Orders, the unknown-ship-date note, entering the Prime fee and Audible by hand, and that the Amazon card is no longer imported.
- [ ] The example prompt JSON parses with the importer.
- [ ] The prompt is written to run from Claude Code, which drives Steven's logged-in Chrome through the Claude in Chrome extension and writes the file straight into `transactions/<YYYY-MM>/`. It no longer tells the Chrome side panel to save into the repo, which it cannot do.
- [ ] The README's steps start from Claude Code and end with the dry run in the same session.
- [ ] Fallback documented for when the Chrome connection fails: paste the prompt into the Chrome side panel, ask it to offer the file as a download named `amazon-orders-<run date>.json`, then move it with the one `mv` command shown.

## Comments

- 2026-09-30: On the first run the side panel reported saving into `transactions/2026-09/` but the file existed only in its own sandbox, and Steven had to ask for a download link. Steven chose to run the scrape from Claude Code, with the side panel as the fallback. A scrape of about 60 Orders has not been tried from Claude Code yet, so ticket 15's run is the first test of it.
