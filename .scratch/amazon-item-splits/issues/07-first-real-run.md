# 07: First real run

**What to build:** Steven runs the full workflow once on real data and confirms the two assumptions the spec couldn't settle from code: "For who" fills in for new Item rows the same way it does for card rows, and Amazon's Item positions stay the same between scrapes (the Item key depends on it).

**Blocked by:** 01, 02, 03, 04, 05, 06

**Status:** ready-for-human

- [ ] Run the scrape prompt in logged-in Chrome. The file lands in this month's transactions folder.
- [ ] Dry run: the summary lists Items since 2026-07-29 and all skipped reasons, and at least one multi-Item Order's formula matches its Amazon invoice.
- [ ] Import a small real file. New Item rows show "For who" = All and "Send to Splitwise" ticked.
- [ ] Re-run the scrape and compare Item positions for the same Orders. If they differ, open a follow-up ticket to change the key.
- [ ] Re-import the Chase2222 CSV. Only non-order Charges (e.g. Whole Foods) are added.
