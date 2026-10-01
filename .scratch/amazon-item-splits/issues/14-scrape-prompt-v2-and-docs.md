# 14: Scrape prompt version 2 and docs

**What to build:** The scrape prompt produces schema version 2 files that match what Amazon really shows, and the README describes the new workflow. See the spec addendum.

**Blocked by:** 08, 09, 10, 11, 12, 13

**Status:** resolved

- [x] `scrape-amazon-orders.md` writes `schema_version` 2 with `kind` on every Order.
- [x] Order Total is the total before gift card or points, with the Amazon line named.
- [x] Tax goes on the Order when Amazon shows it once, and on the shipment when shown per shipment.
- [x] Ship date is the "Package left the shipper facility" date, `null` when tracking is gone.
- [x] A coupon with no visible targets is recorded with `positions: []`.
- [x] Refunds list `positions`, including one Refund that covers several Items.
- [x] Whole Foods Orders are found by walking the Orders list (not the search box) and recorded with `charges`, `discounts`, `delivered`, and the Order Total.
- [x] The Digital Orders tab is read, with the card taken from each details page.
- [x] Only Steven's own account is read, never another account's Orders.
- [x] The README covers Whole Foods and Digital Orders, the unknown-ship-date note, entering the Prime fee and Audible by hand, and that the Amazon card is no longer imported.
- [x] The example prompt JSON parses with the importer.
- [x] The prompt is written to run from Claude Code, which drives Steven's logged-in Chrome through the Claude in Chrome extension and writes the file straight into `transactions/<YYYY-MM>/`. It no longer tells the Chrome side panel to save into the repo, which it cannot do.
- [x] The README's steps start from Claude Code and end with the dry run in the same session.
- [x] Fallback documented for when the Chrome connection fails: paste the prompt into the Chrome side panel, ask it to offer the file as a download named `amazon-orders-<run date>.json`, then move it with the one `mv` command shown.

## Comments

- 2026-09-30: On the first run the side panel reported saving into `transactions/2026-09/` but the file existed only in its own sandbox, and Steven had to ask for a download link. Steven chose to run the scrape from Claude Code, with the side panel as the fallback. A scrape of about 60 Orders has not been tried from Claude Code yet, so ticket 15's run is the first test of it.
- 2026-10-01 Open question: where does the README live? Went with: updating `transactions/README.md` (the only README in the repo, extended by ticket 06), no new root `README.md`. Why: it already holds the setup, Amazon workflow, and flag docs; a second README would split the single source of truth.
- 2026-10-01 Open question: does the prompt itself run the dry run, or only the README? Went with: the prompt's last step runs `--dry-run` (never a real import) and reports the summary; the README tells Steven to read it and then import. Why: the ticket wants the Claude Code session to end with the dry run; the side-panel variant skips it since it cannot run commands.
- 2026-10-01 Open question: keep `status` on physical Orders? Went with: dropped it from the prompt and example. Why: the importer never reads it and the addendum's version 2 sample omits it; less for the scraper to copy.
- 2026-10-01 Open question: a Refund on a Digital Order. Went with: the prompt tells the agent not to record it and to list it in the report. Why: the importer skips it with a warning anyway (ticket 13); leaving it out of the file avoids a warning that cannot be acted on.
- 2026-10-01 Open question: Whole Foods lines that show 0.00. Went with: the prompt says to list every summary line Amazon shows, including 0.00 lines. Why: the importer writes every line into the formula (ticket 12), and "copy every line" needs no judgment from the scraper.
- 2026-10-01 Open question: how does the prompt say "never another account's Orders" without inventing Amazon UI? Went with: a generic rule to stop and tell Steven if the signed-in account is not his or a page lists another account's Orders. Why: the spec gives the rule but no page detail for spotting it.
- 2026-10-01 Open question: test location. Went with: one test in `tests/test_adapter_amazon.py` that extracts the first json block under "### File format (schema version 2)" from the prompt and parses it. Why: keeps it beside the other adapter tests; it fails if the heading or example drifts from what the importer accepts.
