# 13: Digital Orders

**What to build:** A Digital Order (for example the monthly Grocery Subscription) becomes one sheet row, so it no longer depends on importing the Amazon card. See spec addendum decision 9.

**Blocked by:** 08

**Status:** ready-for-agent

- [ ] An Order with `kind: "digital"` writes one row: description is its `short_name`, date is `charge_date`, Amount is `order_total` as a plain number, key `amazon <order number>`, Payment Method as for Items.
- [ ] The cutoff compares the charge date.
- [ ] A re-scrape writes nothing.
- [ ] Adapter-seam tests cover the row and the cutoff. A CLI-seam test covers the re-scrape.
