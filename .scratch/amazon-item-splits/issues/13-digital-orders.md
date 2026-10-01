# 13: Digital Orders

**What to build:** A Digital Order (for example the monthly Grocery Subscription) becomes one sheet row, so it no longer depends on importing the Amazon card. See spec addendum decision 9.

**Blocked by:** 08

**Status:** resolved

- [x] An Order with `kind: "digital"` writes one row: description is its `short_name`, date is `charge_date`, Amount is `order_total` as a plain number, key `amazon <order number>`, Payment Method as for Items.
- [x] The cutoff compares the charge date.
- [x] A re-scrape writes nothing.
- [x] Adapter-seam tests cover the row and the cutoff. A CLI-seam test covers the re-scrape.

## Comments

- 2026-10-01 Open question: a Refund on a Digital Order (it has no Items and `positions` is not `[]` by rule)? Went with: skipped under "refund on Digital Order" with a warning naming the Order and amount ("enter it by hand"), whatever its `positions`. Why: the addendum allows an Order-level Refund only for Whole Foods; a subscription refund is rare, and a loud skip is safer than guessing. Easy to extend the ticket 12 Refund path later.
- 2026-10-01 Open question: a missing or malformed `charge_date`, or an empty `short_name`? Went with: an error naming the Order (the whole import fails), not a skip and not a fallback to another date. Why: the row's date and description come only from these; same loud failure as a missing `order_date` on other kinds.
- 2026-10-01 Open question: does a Digital Order check anything besides the cutoff before writing (delivered, total)? Went with: no. The cutoff (charge date) is checked first so an old Order never errors on its other fields, then the row is written with `order_total` as a plain number (no formula). Why: there are no lines to sum, so no total check; nothing to ship, so never "not ready".
