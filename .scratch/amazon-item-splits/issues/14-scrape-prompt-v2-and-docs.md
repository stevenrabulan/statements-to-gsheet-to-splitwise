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
