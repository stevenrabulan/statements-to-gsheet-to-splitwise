# 15: First real run

**What to build:** Steven runs the full workflow once on real data and confirms the two assumptions the spec couldn't settle from code: "For who" fills in for new Item rows the same way it does for card rows, and Amazon's Item positions stay the same between scrapes (the Item key depends on it).

**Blocked by:** 01, 02, 03, 04, 05, 06, 08, 09, 10, 11, 12, 13, 14

**Status:** done

- [x] Run the scrape prompt from Claude Code, driving logged-in Chrome. The file lands in this month's transactions folder without a download step.
- [x] Dry run: the summary lists Items since 2026-07-29 and all skipped reasons, and at least one multi-Item Order's formula matches its Amazon invoice.
- [x] Import a small real file. New Item rows show "For who" = All and "Send to Splitwise" ticked.
- [x] Whole Foods Orders and the Grocery Subscription each appear as one row, and a Whole Foods row's formula matches its Order page. (Checked in the dry run and in the sheet.)
- [x] Re-run the scrape and compare Item positions for the same Orders. If they differ, open a follow-up ticket to change the key. (They differ. See ticket 17.)

## Comments

- 2026-09-30: Dropped the step "Re-import the Chase2222 CSV". Steven no longer imports the Amazon card (grilling, Q10).
- 2026-09-30: First scrape done on schema version 1 (60 Orders, 2 Refunds). It exposed the gaps now covered by the spec addendum and tickets 08 to 14. The run restarts after 14 with a fresh version 2 scrape.
- 2026-10-01: Renumbered from 07 to 15 so the number matches the order of work. It runs last, after 08 to 14. There is no ticket 07 any more.
- 2026-10-01: Version 2 scrape and dry run done from Claude Code. File: `transactions/2026-10/amazon-orders-2026-10-01.json` (63 physical, 4 Whole Foods, 3 Digital Orders, 2 Refunds). Dry run: 58 rows to append, no total mismatch. Skipped: 13 not ready, 25 unknown ship date, 4 before 2026-07-29, 1 refund before 2026-07-29. Order `111-0000000-0000105` (4 Items, 2 shipments, coupon) sums to its Grand Total of 44.96. The import step is still open: it writes to the sheet, so it waits for Steven.
- 2026-10-01: `accounts.json` had no `amazon-orders` entry. Added it with `ignore_before` 2026-07-29 (the file is not in git).
- 2026-10-01: Item positions are not stable. 4 of 14 Orders with several Items changed their Item order between page loads seconds apart. Opened ticket 17.
- 2026-10-01: Gaps in the scrape prompt found on real pages. Each needs a decision before the next scrape:
  - **Order Total with a gift card.** Amazon shows no total above "Gift Card Amount", only "Total before tax" and "Estimated tax to be collected". For `111-0000000-0000102` and `111-0000000-0000106` the scraper added those two lines (27.20 and 56.86). The prompt says to copy a line that does not exist.
  - **Purchases made in a Whole Foods store** ("Purchased at Whole Foods Market") are in the Orders list, paid with the card ending 2222. They were recorded as Whole Foods Orders with "Item Subtotal", "Tax and Fees", and "Total Savings". The prompt only describes Orders placed through Amazon.
  - **"Free Shipping" line.** Amazon shows "Shipping & Handling 2.99" and "Free Shipping -2.99". Recorded as `shipping: 0` with no discount, which keeps the formulas short.
  - **"Exclusive Promotion Applied"** names no Items. Recorded as a Promo with `positions: []`, like "Your Coupon Savings".
  - **Ship date on a delivered shipment with no "Track package" link** (older Orders, same-day grocery delivery, returned Items) is `null`. 25 Items placed 2026-07-03 to 2026-07-28 were skipped for this reason. Some of them were delivered 2026-07-30 or 2026-07-31, so they may have shipped on or after the Cutoff Date.
  - **Refund dates.** The order details page shows "Refund Total" but no date. The date is on the "View return/refund status" page, and only for returned Items. A refund with no return (5.69 on grocery Order `111-0000000-0000107`) shows no date anywhere the scraper could read, so it is not in the file.
- 2026-10-01: To enter by hand: the 5.69 refund above; the 27.04 refund on `111-0000000-0000104` (before the cutoff, skipped by the importer); and a charge of 16.23 against that same Order on 2026-09-30, shown on the Your Payments page (the socks return is still "in transit").
- 2026-10-02: Imported `transactions/2026-10/amazon-orders-2026-10-01.json` (schema version 3, ASIN keys from ticket 17): 58 rows, sheet rows 940 to 997. Read back from the sheet: all 58 have "Send to Splitwise" ticked and "For who" = All. Both Whole Foods rows (135.12 in store, 113.99 delivery) and both Grocery Subscription rows (9.99) are one row each.
