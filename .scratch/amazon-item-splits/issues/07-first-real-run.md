# 07: First real run

**What to build:** Steven runs the full workflow once on real data and confirms the two assumptions the spec couldn't settle from code: "For who" fills in for new Item rows the same way it does for card rows, and Amazon's Item positions stay the same between scrapes (the Item key depends on it).

**Blocked by:** 01, 02, 03, 04, 05, 06, 08, 09, 10, 11, 12, 13, 14

**Status:** ready-for-human

- [ ] Run the scrape prompt in logged-in Chrome. The file lands in this month's transactions folder.
- [ ] Dry run: the summary lists Items since 2026-07-29 and all skipped reasons, and at least one multi-Item Order's formula matches its Amazon invoice.
- [ ] Import a small real file. New Item rows show "For who" = All and "Send to Splitwise" ticked.
- [ ] Whole Foods Orders and the Grocery Subscription each appear as one row, and a Whole Foods row's formula matches its Order page.
- [ ] Re-run the scrape and compare Item positions for the same Orders. If they differ, open a follow-up ticket to change the key.

## Comments

- 2026-09-30: Dropped the step "Re-import the Chase2222 CSV". Steven no longer imports the Amazon card (grilling, Q10).
- 2026-09-30: First scrape done on schema version 1 (60 Orders, 2 Refunds). It exposed the gaps now covered by the spec addendum and tickets 08 to 14. The run restarts after 14 with a fresh version 2 scrape.
