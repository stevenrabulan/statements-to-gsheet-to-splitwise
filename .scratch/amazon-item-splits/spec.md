# Amazon Item splits

Status: ready-for-agent

Domain terms (Account, Charge, Order, Item, Loaded Cost, Promo, Adjustment, Refund, Share Type, Cutoff Date) are defined in `CONTEXT.md`. Decisions are recorded in ADR 0001 (Amazon spending recorded per Item from Order data) and ADR 0002 (the scraper records facts, Python calculates, and the sheet shows the math).

## Problem Statement

Most of Steven's Amazon spending goes on the Amazon card. When the card's CSV is imported, each Amazon Charge shows up as a code like `AMAZON MKTPL*Y25EQ0CT3`. The code says nothing about what was bought, so Steven can't tell which Charges to share with Partner. Amazon also charges per shipment, not per Order, so one Charge can cover a mix of Personal, Shared, and Partner's Items.

An earlier Claude in Chrome automation scraped Amazon order history and logged Order totals, which made Orders identifiable. It still left the hard part manual: when only some Items in an Order are shared, Steven had to work out each Item's cost by hand, including its tax, its Promos, and its share of shipping. He then typed the result as a formula like `=115.78-90`.

## Solution

Amazon spending is recorded as **one sheet row per Item**, with its Loaded Cost built from scraped Order data.

1. Once per billing cycle, Steven runs a Claude in Chrome prompt kept in this repo. It reads the last 90 days of Amazon Orders and saves exactly what Amazon shows into a JSON file in the month's transactions folder. It performs no arithmetic.
2. Steven imports that file with the existing CLI, the same way as a card CSV, and previews first with `--dry-run`.
3. The importer calculates every Item's Loaded Cost. It checks the costs against Amazon's Order total and writes one row per Item. The Amount cell holds a formula that shows the arithmetic, e.g. `=2*12.99-3+1.81+0.42`.
4. New Items default to Shared. In the sheet, Steven unticks "Send to Splitwise" for Personal Items and sets "For who" to Partner for Partner's Items.
5. When an Item is returned or partially refunded, a later scrape imports a negative row for it. That row copies the original Item's classification.
6. Card imports drop Amazon physical-order Charges, so the same money is never counted twice. Other Charges on the Amazon card, such as Whole Foods, Prime, Kindle, and Audible, still import normally.

## User Stories

1. As Steven, I want each Amazon Item on its own sheet row, so that I can decide per Item whether it is Personal, Shared, or Partner's.
2. As Steven, I want each Item row's Amount to be its full Loaded Cost (price, Promos, tax, and its share of shipping), so that splitting an Item splits exactly what it cost me.
3. As Steven, I want the Amount written as a formula of dollar amounts, so that I can see how each cost was built without trusting a hidden calculation.
4. As Steven, I want the formula terms in a fixed order (quantity × price, minus Promos, plus tax, plus shipping share, plus any whole-Order discount share), so that every Amazon row reads the same way.
5. As Steven, I want zero-value terms left out of the formula and a quantity of 1 written without a multiplier, so that formulas stay short.
6. As Steven, I want a Promo to reduce only the Items it targets, so that a coupon on one product doesn't make shared Items look cheaper.
7. As Steven, I want a Promo that targets several Items spread across them in proportion to their price, so that each targeted Item gets a fair part.
8. As Steven, I want Amazon's per-Item tax used whenever Amazon shows it, so that tax is exact where possible.
9. As Steven, I want shipment tax spread across that shipment's Items in proportion to their price after Promos when per-Item tax isn't shown, so that tax is still allocated sensibly.
10. As Steven, I want a single-Item shipment to take its shipment's tax exactly, so that the common case has no estimation at all.
11. As Steven, I want shipping spread across Items in proportion to their price after Promos, so that shipping is shared fairly.
12. As Steven, I want a discount on the whole Order treated like shipping (spread across all Items in proportion to price), so that Order-wide savings benefit every Item.
13. As Steven, I want each Order's Item costs to add up exactly to the Order total, with the leftover cent assigned to the largest part, so that nothing is lost or invented by rounding.
14. As Steven, I want an Order whose calculated costs don't match Amazon's Order total to be skipped with a warning, so that a bad scrape never writes wrong numbers.
15. As Steven, I want how an Order was paid (gift card, points, card) to have no effect on Loaded Cost, so that shared costs reflect the true price.
16. As Steven, I want the Payment Method column set from the card on the Order, matched by its last four digits to my accounts config, so that rows say "Amazon Card" like everything else.
17. As Steven, I want Orders paid entirely by gift card or points labelled "Amazon Gift Card" or "Points", so that I can tell them apart.
18. As Steven, I want an Order paid partly by gift card and partly by card labelled with the card, so that labels stay consistent.
19. As Steven, I want an unmatched payment card to fall back to the Amazon config entry's name with a warning, so that the import doesn't fail and I know to fix my config.
20. As Steven, I want Order Date (column A) to be the date the Order was placed, so that it matches the column header.
21. As Steven, I want the Item column to show the brand and a plain description in normal case (e.g. "Glad ForceFlex Trash Bags"), so that I can recognize the product at a glance.
22. As Steven, I want a quantity above 1 shown as a prefix (e.g. "2× Glad ForceFlex Trash Bags"), so that multi-packs are obvious.
23. As Steven, I want new Item rows to default to Shared (ticked, For who as card rows get today), so that I only touch the exceptions.
24. As Steven, I want Personal Items written to the sheet with "Send to Splitwise" unticked (after I untick them), so that each Order stays fully recorded and I can reclassify later.
25. As Steven, I want an Order imported only once every non-cancelled Item has shipped, so that split shipments, cancellations, and recalculated tax never produce wrong rows.
26. As Steven, I want cancelled Items skipped, so that I'm never charged for something that didn't ship.
27. As Steven, I want Orders that aren't ready to be reported and picked up on a later scrape, so that nothing is silently lost.
28. As Steven, I want every Item row to carry a stable key (order number and Item position) in the Notes column, so that re-scraping an Order never duplicates rows.
29. As Steven, I want Amazon rows deduplicated by that key rather than by date, amount, and description, so that a one-cent change on re-scrape doesn't create a duplicate.
30. As Steven, I want a returned or refunded Item imported as a negative row for the refund amount Amazon shows, so that Splitwise credits come out right.
31. As Steven, I want a Refund row to copy "Send to Splitwise" and "For who" from the original Item row, so that a Shared return credits Partner and a Personal return stays out of Splitwise.
32. As Steven, I want a Refund row dated on the refund date, so that it lands in the billing cycle when the money came back.
33. As Steven, I want a Refund for an Item imported in the same run to take that Item's default classification, so that returns during one scrape window still work.
34. As Steven, I want each Refund to carry its own stable key, so that re-scraping doesn't duplicate Refunds and several partial refunds on one Item stay distinct.
35. As Steven, I want a Refund on an Order from before the Cutoff Date skipped with a warning that shows the Order and amount, so that I can enter it by hand.
36. As Steven, I want Amazon Items that shipped before the Cutoff Date (2026-07-29) ignored, so that Orders already recorded as Charge rows aren't counted twice.
37. As Steven, I want the cutoff compared against the shipment's ship date, not the Order Date, so that an Order placed before the cutoff but shipped after it isn't missed.
38. As Steven, I want the Amazon Cutoff Date set in my accounts config in the same shape as my other cards, so that there's one place for these settings.
39. As Steven, I want the dry-run summary to report how many Items were skipped for the cutoff, for not being ready, and for failing the total check, so that I can see everything the import left out.
40. As Steven, I want card imports to drop `Amazon.com*`, `AMAZON MKTPL*`, and `AMZN Mktp*` Charges (and their refund credits) on every Account, so that Amazon Orders are counted only once.
41. As Steven, I want those dropped Charges counted in the per-file summary, so that I can see the filter worked.
42. As Steven, I want Whole Foods, Prime membership, Prime Video, Kindle, and Audible Charges to keep importing from the Amazon card CSV, so that non-order spending isn't lost.
43. As Steven, I want the scrape to cover the last 90 days of Orders, so that late shipments and returns are caught and the first run reaches back to the Cutoff Date.
44. As Steven, I want the scrape started manually from a prompt file in this repo, so that it runs in my logged-in Chrome when I choose.
45. As Steven, I want the scrape prompt to record only what Amazon shows and calculate nothing, so that LLM arithmetic errors can't reach the sheet.
46. As Steven, I want the scrape to record both the full product title and a short name, so that the sheet is readable and the full title is kept for reference.
47. As Steven, I want the scraped file saved in the month's transactions folder with a name that matches my Amazon config entry, so that the existing CLI routes and imports it.
48. As Steven, I want JSON files in a folder picked up by the CLI alongside CSVs and PDFs, so that one command imports the whole month.
49. As Steven, I want `--dry-run`, `--from`/`--to`, `--force`, and the import log to work for Amazon files as they do for cards, so that I use one familiar workflow.
50. As Steven, I want the old order-total prompt replaced by the new scrape prompt, so that there's only one Amazon workflow.

## Implementation Decisions

**Scrape prompt (replaces the old order-total prompt)**
- A markdown prompt for Claude in Chrome, run manually.
- It reads Amazon order history for the last 90 days and opens each Order's details or invoice page.
- It records raw facts only, never totals or allocations it has calculated.
- It writes one JSON file per run into the current month's transactions folder, named so that it contains the Amazon accounts-config key (e.g. `amazon-orders-<run date>.json`).
- It includes rules for the short name: the brand plus a plain description, in normal case, without made-up abbreviations.

**Scraped file contents (the contract between the scraper and the importer)**
- **Per Order:** order number, Order Date, status, payment description (card type and last four, gift card, points, or a combination), the Order total Amazon shows, shipping amount(s), and whole-Order discounts.
- **Per shipment:** status (shipped or not, with ship date), the tax Amazon shows for it, and the Items in it.
- **Per Item:** position within the Order, full title, short name, quantity, unit price, cancelled flag, the Promos that target it (name and amount), and its own tax if Amazon shows it.
- **Per Refund:** which Item (order number and position), amount, and refund date.
- The file carries a schema version so that later prompt changes can be detected.
- **Promos are recorded per Order, not per Item** (decided in ticket 02). Each Promo lists the positions of the Items it targets, so a Promo on several Items carries one total that the importer spreads. Recording a copy on each Item would repeat or split that total.

**Schema version 1** (fixture: `tests/fixtures/amazon-orders-sample.json`). All amounts are positive dollar numbers as Amazon shows them. Promos and discounts are amounts taken off.

```json
{
  "schema_version": 1,
  "scraped_on": "2026-09-28",
  "orders": [{
    "order_number": "111-0000000-0000001",
    "order_date": "2026-08-03",
    "status": "Delivered",
    "payment": [{"type": "card", "card_type": "Visa", "last_four": "4242"},
                {"type": "gift_card"}],
    "order_total": 30.95,
    "shipping": 5.99,
    "discounts": [{"name": "Subscribe & Save", "amount": 1.50}],
    "promos": [{"name": "Save $3 with coupon", "amount": 3.00, "positions": [1, 2]}],
    "shipments": [{
      "shipped": true,
      "ship_date": "2026-08-04",
      "tax": 1.81,
      "shipping": null,
      "items": [{
        "position": 1,
        "title": "Fakebrand ForceFlex Tall Kitchen Drawstring Trash Bags, 13 Gallon, 80 Count",
        "short_name": "Fakebrand ForceFlex Trash Bags",
        "quantity": 2,
        "unit_price": 12.99,
        "cancelled": false,
        "tax": null
      }]
    }]
  }],
  "refunds": [{"order_number": "111-0000000-0000001", "position": 1,
               "amount": 12.99, "refund_date": "2026-08-20"}]
}
```

- `payment[].type` is `card`, `gift_card`, or `points`. Only `card` has `card_type` and `last_four` (4 digits).
- `shipping` on the Order is required (0 when free). `shipping` on a shipment is `null` unless Amazon shows shipping per shipment.
- An Item's `tax` is `null` unless Amazon shows per-Item tax.

**Amazon adapter (new)**
- Recognized by file type (JSON) and routed like the other adapters. The CLI's folder expansion includes `.json` files.
- It receives the matched account config (name and Cutoff Date) and the full accounts map for Payment Method matching. This extends the adapter's signature compared with the CSV adapters.
- **Readiness:** an Order is processed only when every non-cancelled Item's shipment has shipped. Otherwise it is skipped with the reason "not ready". Cancelled Items are dropped.
- **Cutoff:** Items whose shipment ship date is before the Cutoff Date are skipped. The generic cutoff filter in the CLI, which compares the row date, must not also apply to Amazon rows.
- **Loaded Cost calculation (in this order):**
  1. Line price = quantity × unit price.
  2. Each Promo is spread across the Items it targets in proportion to their line price.
  3. Net price = line price minus that Item's Promo shares.
  4. Tax = the Item's own tax if shown. Otherwise the shipment's tax is spread across that shipment's non-cancelled Items in proportion to net price.
  5. Shipping and whole-Order discounts are each spread across the Order's Items in proportion to net price, using the smallest scope Amazon shows (shipment or Order).
  6. Each spread component is rounded to cents so that its parts sum exactly to the source amount. The leftover cent goes to the largest part.
  7. The sum of the Order's Loaded Costs must equal the Order total Amazon showed (for the non-cancelled Items). Otherwise the whole Order is skipped with a warning naming the Order, the expected total, and the calculated total.
- **Amount formula:** the terms are quantity × unit price, minus the Promo share, plus tax, plus the shipping share, plus the whole-Order discount share (written as a subtraction). Zero terms are omitted and a quantity of 1 has no multiplier. Every term is a rounded dollar amount, and the formula's value equals the Loaded Cost.
- **Payment Method:** the payment's last four digits are matched against accounts-config keys that contain those digits, and the result is that account's name. Gift card only gives "Amazon Gift Card", and points only gives "Points". A card plus gift card gives the card. With no match, the Amazon entry's name is used and a warning is added.
- **Refunds:** each becomes a negative-amount row dated on the refund date, with a plain negative amount (no component formula). A Refund whose Item shipped before the Cutoff Date is skipped with a warning that lists the order number and amount.

**Row shape and the Transaction model**
- The Transaction model gains optional fields: an amount formula, a stable Amazon key, "Send to Splitwise", and "For who". Card rows leave them unset and behave exactly as today.
- The sheet row builder writes the formula into Amount when one is present. Writes already use user-entered input, so formulas evaluate.
- Item rows leave "Send to Splitwise" and "For who" as card rows do today (ticked, and the sheet's usual For who). Refund rows write both values explicitly, copied from the original Item row.
- **Notes (column K):** Item rows hold `split-transactions automation amazon <order number> #<position>`. Refund rows hold `split-transactions automation amazon <order number> #<position> refund <refund date> <amount>`. The key is the part after `split-transactions automation `.

**Deduplication**
- Amazon rows are deduplicated by the key in Notes: any existing sheet row whose Notes contain the key counts as a match. The generic date/amount/description/account key is not used for Amazon rows.
- To look up Refund classifications, the importer finds the existing row whose Notes contain the Item key and reads its E and H values. If the Item is being imported in the same run, the Refund uses that Item's defaults.

**Card import filter**
- After any non-Amazon adapter parses a file, Charges whose description starts with `Amazon.com*`, `AMAZON MKTPL*`, or `AMZN Mktp*` (case-insensitive) are dropped, for every Account and for both debits and credits. They are counted under a skipped reason such as "amazon order charge".
- Descriptors for Whole Foods, Prime, Prime Video, Kindle, and Audible are not matched.

**Configuration**
- An accounts-config entry for Amazon Orders in the existing object form: a key matching the scraped filename, name "Amazon" (used only as the Payment Method fallback), and Cutoff Date 2026-07-29.
- The example config and README document the Amazon entry, the scrape workflow, and the card filter.

## Testing Decisions

- Tests exercise external behavior only: files in, rows out. They don't test private helpers or the order of internal steps. Each test uses a small synthetic JSON fixture with made-up order numbers and products, never real Order data.

**Seam 1: the Amazon adapter's parse** (prior art: the existing per-adapter tests for Fakecoin, Discover, Chase credit, and Chase checking). It takes a fixture and asserts on the resulting Item rows (formula, value, description, Payment Method, key), the skipped reasons, and the warnings. Cases:
- a single Item with per-Item tax
- a multi-Item shipment with shipment tax spread across Items
- a Promo targeting one Item, and a Promo targeting several Items
- shipping and a whole-Order discount spread across Items
- a rounding remainder assigned to the largest part
- a mismatch with the Order total, so the Order is skipped with a warning
- an Order that isn't ready
- a cancelled Item
- quantity above 1
- zero terms left out of the formula
- Payment Method: a card match, gift card only, points only, a split tender, and an unmatched card
- the ship-date cutoff, including an Order placed before the cutoff that shipped after it
- a Refund row (date, negative amount, key)
- a Refund on an Order from before the cutoff

**Seam 2: the CLI's run** with the sheet reads and writes faked (prior art: the existing CLI tests that patch the sheet read and append). Rows are asserted after the row builder runs, so the Amount formula and the E, H, and K cells are checked. Cases:
- a folder containing a JSON file is imported
- a re-scrape of already-imported Items writes nothing
- a Refund copies a Personal row's unticked E and a Partner row's H
- a Refund for an Item in the same run takes the defaults
- a Chase CSV with Amazon order Charges and a Whole Foods Charge writes only Whole Foods, and the summary counts the dropped Charges
- the generic cutoff isn't applied a second time to Amazon rows
- a dry run writes nothing and leaves the import log untouched

## Out of Scope

- Reconciling Amazon Order totals against card Charges (Steven no longer imports Amazon order Charges).
- Running the scrape on a schedule.
- Digital Orders (Kindle, Prime Video, Audible, apps) and Prime membership as Items. They stay as card Charge rows.
- Item-level detail for Whole Foods or other non-order Charges.
- Amazon's "Request Your Data" export as a data source.
- Automatic classification rules (e.g. remembering that a product is always Personal).
- Changing rows that were already imported when an Order changes later. Price adjustments arrive as Refunds.
- Converting historical Amazon Charge rows (before 2026-07-29) into Item rows.
- Any change to the Splitwise sync or to the sheet's formulas outside the rows being written.

## Further Notes

- **Known gap:** untaxed Items (most groceries in Texas) in a mixed shipment absorb part of the shipment's tax when Amazon doesn't show per-Item tax. This was accepted as a cents-level error.
- **Risk:** the Item key uses the Item's position in the Order. If Amazon reorders Items between scrapes, a re-scrape could produce duplicate rows. The implementer should check that Amazon's Item order is stable across page loads and flag it if not.
- The first run needs the 90-day window to reach back to the Cutoff Date (2026-07-29). A run in late September covers this.
- Default classification relies on the sheet filling "For who" the same way it does for card rows today. The implementer should confirm this with one real dry run followed by one real import of a small file.

## Addendum 2026-09-30: findings from the first real scrape

The first real scrape (60 Orders, 2 Refunds) showed gaps between what Amazon displays and schema version 1. These decisions come from the grilling session that followed. New terms (Whole Foods Order, Digital Order, Order Total) are in `CONTEXT.md`. Where this addendum disagrees with the text above, the addendum wins.

### Decisions

1. **Tax shown only for the whole Order.** Multi-shipment Orders show one tax figure. The file records it on the Order. When a shipment's tax is `null`, the importer spreads the Order's tax across all the Order's non-cancelled Items in proportion to price after Promos (shipping not included in the weights).
2. **Ship date.** Amazon shows no "Shipped" date. The scraper uses the date of the "Package left the shipper facility" tracking event, and `null` when tracking is gone.
3. **Unknown ship date.** When a shipped shipment's ship date is `null`, the Order Date stands in for the cutoff comparison only. If the Order Date is on or after the Cutoff Date, the Items are imported. If it is before, the Order is skipped with the reason "unknown ship date" and a warning. Each imported row that used the fallback gets a warning in the run output and a Notes suffix after its key: ` (ship date unknown, Order Date used for cutoff)`. Column A is the Order Date either way.
4. **Coupon with unknown targets.** A Promo with `positions: []` is treated as an Adjustment: spread across all Items in proportion to price after Promos, written in the formula's discount term, with a warning naming the Order and amount.
5. **Order Total.** The total before any gift card or points are applied (the line above "Gift Card Amount"), not the "Grand Total" after it.
6. **Refund covering several Items.** A Refund lists `positions`. The importer writes one negative row per Item, splitting the amount in proportion to the Items' Loaded Costs (leftover cent to the largest part). Each row copies its own Item's classification and has its own key.
7. **Whole Foods Orders.** One row per Order, not per Item. Description `Whole Foods`, date is the Order Date, Amount is a formula of the summary lines Amazon shows (e.g. `=106.99+7` for subtotal plus driver tip) and must equal the Order Total, otherwise the Order is skipped with the "total mismatch" warning. Key `amazon <order number>` (no position). Imported once delivered. Cutoff compared with the Order Date. Defaults to Shared. Payment Method as for Items.
8. **Whole Foods Refunds.** A Refund with `positions: []` on a Whole Foods Order becomes one negative row, `Refund: Whole Foods`, key `amazon <order number> refund <refund date> <amount>`, copying the Order row's "Send to Splitwise" and "For who".
9. **Digital Orders.** The scrape reads the Digital Orders tab. One row per Digital Order: description is what was bought (e.g. `Grocery Subscription`), date is the charge date, Amount is the amount shown, key `amazon <order number>` (e.g. `amazon D01-...`), Payment Method from the card on its details page, cutoff compared with the charge date, defaults to Shared.
10. **The Amazon card is no longer imported.** The card-import filter stays as a safety net. The Prime fee (yearly, no charge history shown) and Audible (separate sign-in) are entered by hand.
11. **Scrape scope.** Only Steven's own account, never another account's Orders. Whole Foods Orders are found by walking the 90-day Orders list, not the search box.
12. **Schema version 2.** The importer accepts only version 2, so a file from the old prompt fails with the existing version error.

### Schema version 2 (changes from version 1)

```json
{
  "schema_version": 2,
  "scraped_on": "2026-09-30",
  "orders": [
    {
      "kind": "physical",
      "order_number": "111-0000000-0000001",
      "order_date": "2026-08-03",
      "payment": [{"type": "card", "card_type": "Visa", "last_four": "4242"}],
      "order_total": 30.95,
      "tax": 2.68,
      "shipping": 0,
      "discounts": [],
      "promos": [{"name": "Coupon", "amount": 1.48, "positions": []}],
      "shipments": [{"shipped": true, "ship_date": null, "tax": null, "shipping": null, "items": []}]
    },
    {
      "kind": "whole_foods",
      "order_number": "111-0000000-0000002",
      "order_date": "2026-09-11",
      "delivered": true,
      "payment": [{"type": "card", "card_type": "Visa", "last_four": "4242"}],
      "order_total": 113.99,
      "charges": [{"name": "Subtotal", "amount": 106.99}, {"name": "Driver tip", "amount": 7.00}],
      "discounts": []
    },
    {
      "kind": "digital",
      "order_number": "D01-0000000-0000003",
      "charge_date": "2026-09-09",
      "short_name": "Grocery Subscription",
      "payment": [{"type": "card", "card_type": "Visa", "last_four": "4242"}],
      "order_total": 9.99
    }
  ],
  "refunds": [
    {"order_number": "111-0000000-0000001", "positions": [5, 6], "amount": 27.04, "refund_date": "2026-08-11"},
    {"order_number": "111-0000000-0000002", "positions": [], "amount": 4.99, "refund_date": "2026-09-12"}
  ]
}
```

- `kind` is `physical`, `whole_foods`, or `digital`. Required on every Order.
- `tax` on a physical Order is the Order-level tax, or `null` when Amazon shows tax per shipment. A shipment's `tax` may now be `null`. If both are `null`, the Order's tax is taken as 0 and the total check decides.
- A shipped shipment's `ship_date` may be `null`.
- `positions` replaces `position` on a Refund. It is `[]` only for a Whole Foods Order.
- Whole Foods `charges` are the summary lines Amazon shows that add to the total, and `discounts` the lines that reduce it. The Order Total line itself is not listed in either.

### Changes to earlier sections

- User story 42 and the "Card import filter" note about Whole Foods and digital Charges importing from the card no longer describe the workflow (decision 10).
- Out of Scope: "Digital Orders ... stay as card Charge rows" is replaced by decision 9. "Item-level detail for Whole Foods" stays out of scope (decision 7 records the Order, not its Items).
- Seam 1 gains cases for decisions 1, 3, 4, 6, 7, 8, and 9. Seam 2 gains: a Whole Foods Refund copies the Order row's classification, and a re-scrape of Whole Foods and Digital Orders writes nothing.
