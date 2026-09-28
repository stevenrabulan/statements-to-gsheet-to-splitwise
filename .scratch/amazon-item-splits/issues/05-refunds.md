# 05: Refunds

**What to build:** When Steven returns an Item or gets a partial refund, the next scrape imports a negative row for that Item. The row keeps the Item's classification, so a Shared return credits Partner, a Partner's return credits her in full, and a Personal return stays out of Splitwise. See the spec's "Refunds" and "Deduplication" sections.

**Blocked by:** 02 (Tracer bullet: one simple Amazon Order becomes one Item row), 04 (Readiness and the ship-date cutoff)

**Status:** ready-for-agent

- [ ] Each Refund becomes a row with a plain negative amount (the refund amount Amazon shows), dated on the refund date.
- [ ] Notes hold `split-transactions automation amazon <order number> #<position> refund <refund date> <amount>`. Re-scrapes don't duplicate Refunds, and several partial refunds on one Item stay distinct.
- [ ] The row's "Send to Splitwise" and "For who" are copied from the existing sheet row whose Notes contain the Item's key.
- [ ] If the Item is being imported in the same run, the Refund uses that Item's defaults.
- [ ] A Refund whose Item shipped before the Cutoff Date is skipped with a warning listing the order number and amount.
- [ ] CLI-seam tests cover:
  - [ ] copying an unticked Personal row
  - [ ] copying a Partner row
  - [ ] a same-run Item
  - [ ] a re-scrape with no duplicate Refund
- [ ] An adapter-seam test covers the pre-cutoff Refund warning.
