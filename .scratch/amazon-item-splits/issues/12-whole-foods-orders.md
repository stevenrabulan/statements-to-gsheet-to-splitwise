# 12: Whole Foods Orders

**What to build:** A Whole Foods Order becomes one sheet row for the whole Order, tip included, and a Refund on it becomes one negative row that follows the Order row's classification. See spec addendum decisions 7 and 8.

**Blocked by:** 08, 11

**Status:** ready-for-agent

- [ ] An Order with `kind: "whole_foods"` writes one row: description `Whole Foods`, date is the Order Date, key `amazon <order number>`, Payment Method as for Items.
- [ ] Amount is a formula of `charges` added and `discounts` subtracted (e.g. `=106.99+7`). If it does not equal `order_total`, the Order is skipped under "total mismatch" with the usual warning.
- [ ] `delivered: false` skips the Order under "not ready".
- [ ] The cutoff compares the Order Date.
- [ ] A Refund with `positions: []` on a Whole Foods Order writes `Refund: Whole Foods`, key `amazon <order number> refund <date> <amount>`, and copies the Order row's "Send to Splitwise" and "For who" (defaults when the Order is in the same run).
- [ ] An Order key never matches an Item key or a Refund key of another row, and a re-scrape writes nothing.
- [ ] Adapter-seam and CLI-seam tests cover the row, the mismatch, not delivered, the cutoff, the Refund, and the re-scrape.
