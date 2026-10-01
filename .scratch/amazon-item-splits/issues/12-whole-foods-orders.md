# 12: Whole Foods Orders

**What to build:** A Whole Foods Order becomes one sheet row for the whole Order, tip included, and a Refund on it becomes one negative row that follows the Order row's classification. See spec addendum decisions 7 and 8.

**Blocked by:** 08, 11

**Status:** resolved

- [x] An Order with `kind: "whole_foods"` writes one row: description `Whole Foods`, date is the Order Date, key `amazon <order number>`, Payment Method as for Items.
- [x] Amount is a formula of `additions` added and `discounts` subtracted (e.g. `=106.99+7`). If it does not equal `order_total`, the Order is skipped under "total mismatch" with the usual warning.
- [x] `delivered: false` skips the Order under "not ready".
- [x] The cutoff compares the Order Date.
- [x] A Refund with `positions: []` on a Whole Foods Order writes `Refund: Whole Foods`, key `amazon <order number> refund <date> <amount>`, and copies the Order row's "Send to Splitwise" and "For who" (defaults when the Order is in the same run).
- [x] An Order key never matches an Item key or a Refund key of another row, and a re-scrape writes nothing.
- [x] Adapter-seam and CLI-seam tests cover the row, the mismatch, not delivered, the cutoff, the Refund, and the re-scrape.

## Comments

- 2026-10-01 Open question: how does an Order key avoid matching an Item key or a Refund key that starts with it? Went with: one whole-word `KEY_PATTERN` (`amazon \S+(?: #\d+)?(?: refund \S+ \S+)?`) that takes the longest form, and `ROW_KEY_PATTERN` (Item or Order key, not a Refund's) for the Refund classification lookup. Why: a plain `amazon <order>` pattern would match the front of every Item key in Notes.
- 2026-10-01 Open question: which check runs first on a Whole Foods Order? Went with: delivered, then cutoff (Order Date), then the total check. Why: same order as physical Orders, so an old Order never warns about its totals.
- 2026-10-01 Open question: are zero-amount charge or discount lines left out of the formula as Item terms are? Went with: no, every line Amazon shows is written, charges first then discounts as subtractions; at least one charge is required. Why: ADR 0002 has the sheet show what Amazon showed; the scraper lists only lines on the summary.
- 2026-10-01 Open question: a Whole Foods Refund whose Order is before the cutoff? Went with: skipped under "refund before <cutoff>" with a warning naming the Order and amount, using the Order Date. Why: matches Item Refunds; the Order has no row to copy from.
- 2026-10-01 Open question: a Whole Foods Refund with a non-empty `positions`, or a physical Refund with `positions: []`? Went with: an error naming the Order, as ticket 11 did for physical Orders. Why: the addendum allows `[]` only for Whole Foods Orders.
- 2026-10-01 Open question: a Refund with `positions: []` whose Order is not in the file? Went with: skipped under "refund without item" with a warning (enter by hand), not an error. Why: the Order's kind is unknown, and a missing Order is already a skip for Item Refunds.
- 2026-10-01 Open question: a Whole Foods Refund on an Order that is not delivered? Went with: still imported, held by the CLI until the Order row exists. Why: same as Item Refunds on an Order not ready.
- 2026-10-01 Review follow-up: the schema field `charges` is renamed `additions` in the importer, the scrape prompt, the spec sample, and the tests. Why: in CONTEXT.md a Charge is a posted statement line on an Account, and these are an Order's summary lines that add to its total. Done before the first real scrape (ticket 15), so no file needs migrating.
