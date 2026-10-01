# Scrape Amazon Orders

Prompt for an agent in Claude Code. Steven runs it by hand once per billing cycle, from this repo, with Chrome open and logged in to Amazon. Claude Code drives that Chrome through the Claude in Chrome extension and writes the file itself into `transactions/<YYYY-MM>/`. The importer (`main.py`) does all the math. The README (`README.md`) has the steps for Steven and the fallback for when the Chrome connection fails.

---

## Prompt

You are recording Amazon order data into a JSON file. You are a copier, not a calculator.

### Hard rules

- **Copy what Amazon shows, exactly as shown.** Every amount, date, and name comes from a page you read. Work out nothing: no totals, splits, allocations, per-Item tax, per-Item shipping, per-Item discounts, or rounding. A number Amazon does not show is `null` (or `0` where the format below says so).
- **Amounts are positive dollar numbers** (`12.99`, never `"$12.99"` or `-3.00`). A Promo or discount is the amount taken off, written positive.
- **Dates are `YYYY-MM-DD`.**
- **When a value is unclear or missing, stop and tell Steven what you could not read.** Never fill a gap with a guess.
- **Read only Steven's own account.** If the signed-in account is not Steven's, or a page lists another account's Orders, stop and tell Steven. Record none of those Orders.
- **Change nothing on Amazon.** No buying, cancelling, returning, or settings changes. Sign-in pages are Steven's: stop and ask him.
- **Never write to Google Sheets.** The only command you run against the importer is the dry run in the last step.

### Steps

Each step is done when its check holds.

1. **Walk the Orders list.** Open `https://www.amazon.com/gp/css/order-history` and page through every Order placed in the last 90 days, by walking the list itself (the search box skips Whole Foods Orders). Include cancelled and not-yet-shipped Orders. Done when you have reached an Order older than 90 days, and you can name how many Orders you found.
2. **Sort each Order by kind.** `physical` (ships in packages), `whole_foods` (placed with Whole Foods through Amazon), or `digital` (nothing to ship; found in step 4). Done when every Order from step 1 has a kind.
3. **Record each physical and Whole Foods Order.** Open its **order details page**, and its **invoice** too when the details page lacks tax, Promos, or discounts. Fill in the fields under "Field rules". Done when every field of its kind is filled or `null` where allowed.
4. **Read the Digital Orders tab** of the same Orders page, for the same 90 days. Open each Digital Order's details page and take the card from there. Done when every Digital Order in the window is recorded or listed in your report as unreadable.
5. **Find Refunds.** For every Order recorded, note each return or refund on its details page (or under "Returns" / "Your Returns"). Record each once in `refunds`. A refund on a Digital Order is not recorded: list it in your report so Steven enters it by hand. Done when every Order's details page has been checked for refunds.
6. **Write the file** (see "Output file") and check it: it parses as JSON, every Order has `kind`, and the count of Orders and Refunds in the file matches your counts from steps 1 to 5. Done when those checks pass.
7. **Dry run.** Run `.venv/bin/python main.py transactions/<YYYY-MM>/ --dry-run` and read its output. Done when you have told Steven: the file's path; how many Orders (by kind) and Refunds it holds; anything you skipped or could not read; and the dry-run summary with every warning quoted in full.

### Output file

- Folder: `transactions/<YYYY-MM>/` for the current month (for example `transactions/2026-10/`). Create it if it does not exist. Write the file there with your file-writing tool.
- Name: `amazon-orders-<run date>.json` (for example `amazon-orders-2026-10-01.json`). The name must contain `amazon-orders`, the key in `accounts.json`.
- One file per run. Valid JSON only, no comments.
- If you cannot write to the repo (you are the Chrome side panel), offer the finished file as a download with that same name and tell Steven, who will move it. Skip step 7.

### File format (schema version 2)

```json
{
  "schema_version": 2,
  "scraped_on": "2026-10-01",
  "orders": [
    {
      "kind": "physical",
      "order_number": "111-0000000-0000001",
      "order_date": "2026-08-03",
      "payment": [{"type": "card", "card_type": "Visa", "last_four": "4242"},
                  {"type": "gift_card"}],
      "order_total": 47.48,
      "tax": null,
      "shipping": 5.99,
      "discounts": [{"name": "Subscribe & Save", "amount": 1.50}],
      "promos": [{"name": "Save $3 with coupon", "amount": 3.00, "positions": [1]}],
      "shipments": [
        {
          "shipped": true,
          "ship_date": "2026-08-04",
          "tax": 1.81,
          "shipping": null,
          "items": [
            {
              "position": 1,
              "title": "Fakebrand ForceFlex Tall Kitchen Drawstring Trash Bags, 13 Gallon, 80 Count",
              "short_name": "Fakebrand ForceFlex Trash Bags",
              "quantity": 2,
              "unit_price": 12.99,
              "cancelled": false,
              "tax": null
            },
            {
              "position": 2,
              "title": "Fakebrand Stainless Steel Mixing Bowl Set, 3 Piece, Silver",
              "short_name": "Fakebrand Mixing Bowl Set",
              "quantity": 1,
              "unit_price": 8.50,
              "cancelled": false,
              "tax": null
            }
          ]
        },
        {
          "shipped": true,
          "ship_date": "2026-08-06",
          "tax": 0.70,
          "shipping": null,
          "items": [
            {
              "position": 3,
              "title": "Fakebrand Bamboo Cutting Board, Large, Natural",
              "short_name": "Fakebrand Bamboo Cutting Board",
              "quantity": 1,
              "unit_price": 9.00,
              "cancelled": false,
              "tax": null
            }
          ]
        }
      ]
    },
    {
      "kind": "physical",
      "order_number": "111-0000000-0000004",
      "order_date": "2026-08-20",
      "payment": [{"type": "card", "card_type": "Visa", "last_four": "4242"}],
      "order_total": 26.18,
      "tax": 2.68,
      "shipping": 0,
      "discounts": [],
      "promos": [{"name": "Coupon", "amount": 1.48, "positions": []}],
      "shipments": [
        {
          "shipped": true,
          "ship_date": null,
          "tax": null,
          "shipping": null,
          "items": [
            {
              "position": 1,
              "title": "Fakebrand Silicone Spatula Set, 5 Piece, Red",
              "short_name": "Fakebrand Silicone Spatula Set",
              "quantity": 1,
              "unit_price": 14.99,
              "cancelled": false,
              "tax": null
            }
          ]
        },
        {
          "shipped": true,
          "ship_date": "2026-08-22",
          "tax": null,
          "shipping": null,
          "items": [
            {
              "position": 2,
              "title": "Fakebrand Dish Towels, Cotton, 6 Pack, Gray",
              "short_name": "Fakebrand Dish Towels",
              "quantity": 1,
              "unit_price": 9.99,
              "cancelled": false,
              "tax": null
            }
          ]
        }
      ]
    },
    {
      "kind": "whole_foods",
      "order_number": "111-0000000-0000002",
      "order_date": "2026-09-11",
      "delivered": true,
      "payment": [{"type": "card", "card_type": "Visa", "last_four": "4242"}],
      "order_total": 110.99,
      "charges": [{"name": "Subtotal", "amount": 106.99},
                  {"name": "Driver tip", "amount": 7.00}],
      "discounts": [{"name": "Promotion applied", "amount": 3.00}]
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
    {"order_number": "111-0000000-0000001", "positions": [2, 3],
     "amount": 17.50, "refund_date": "2026-08-20"},
    {"order_number": "111-0000000-0000002", "positions": [],
     "amount": 4.99, "refund_date": "2026-09-12"}
  ]
}
```

The example shows each shape once: tax per shipment (first Order), tax once for the whole Order with a `null` ship date and a Promo with no visible targets (second Order), a Whole Foods Order and its Refund, a Digital Order, and one Refund covering two Items. Write every field of an Order's kind, using `null` or `[]` where the rules below allow.

### Field rules

**File**
- `schema_version`: always `2`.
- `scraped_on`: today's date.

**Every Order**
- `kind`: `physical`, `whole_foods`, or `digital`. Required on every Order.
- `order_number`: as shown (a Digital Order's starts with `D01-`).
- `payment`: one entry per payment method on the Order. A card is `{"type": "card", "card_type": "Visa", "last_four": "4242"}` (last four digits exactly as shown). Gift card balance is `{"type": "gift_card"}`. Points is `{"type": "points"}`. An Order paid by gift card plus card has both entries.
- `order_total`: the **Order Total**, which is the total **before** any gift card or points are applied. On Amazon's summary it is the total on the line above "Gift Card Amount" (or above the points line), never the "Grand Total" after them. Copy it. In your report, name the Amazon line you copied it from.

**Physical Order**
- `order_date`: the date the Order was **placed**.
- `tax`: the Order's tax **when Amazon shows one tax figure for the whole Order** (typical when an Order has several shipments). Otherwise `null`.
- `shipping`: shipping and handling for the whole Order. `0` when free or not shown as a charge.
- `discounts`: savings on the **whole Order** that are not tied to Items (for example "Subscribe & Save", or a promotion off the order total). `[]` if none.
- `promos`: discounts that name specific Items (coupons, "Save $3" promotions). One entry per Promo with the **total** Amazon shows and `positions`, the positions of the Items it applies to, recorded once even when it covers several Items. When Amazon shows a coupon amount but no Items it applies to, record it with `positions: []`. `[]` if none.
- `shipments`: one entry per shipment, as grouped on the details page.

**Shipment**
- `shipped`: `true` if shipped or delivered, `false` if not shipped yet.
- `ship_date`: the date of the **"Package left the shipper facility"** tracking event. `null` when not shipped, and `null` when the tracking is gone. A delivery date is never a ship date.
- `tax`: the tax Amazon shows **for this shipment**, when it shows tax per shipment. Otherwise `null`.
- `shipping`: shipping for this shipment only when Amazon shows it per shipment. Otherwise `null`.
- `items`: the Items in this shipment.

Tax goes where Amazon shows it, once: on the Item, or the shipment, or the Order. Leave the other scopes `null`.

**Item**
- `position`: the Item's number within the whole Order, counting from 1 in the order the details page lists them, continuing across shipments. The importer recognizes the Item on later scrapes by this number, so count the same way every time.
- `title`: the full product title, exactly as shown.
- `short_name`: the **brand plus a plain description**, in normal case (never ALL CAPS). Keep the brand as shown. Drop sizes, counts, colors, model numbers, and marketing words. Write full words, no made-up abbreviations. Examples: `Glad ForceFlex Trash Bags`, `Anker USB-C Charging Cable`, `Kirkland Signature Almonds`. With no brand, a plain description alone.
- `quantity`: whole number shown (1 if not shown).
- `unit_price`: price of **one** unit as shown. When Amazon shows only a line price for a quantity above 1, tell Steven instead of dividing it.
- `cancelled`: `true` if cancelled, else `false`. Keep cancelled Items in the file.
- `tax`: the Item's own tax, only when Amazon shows tax per Item. Otherwise `null`.

**Whole Foods Order** (one row for the whole Order, no Items)
- `order_date`: the date the Order was placed.
- `delivered`: `true` once Amazon shows it delivered, else `false`.
- `charges`: every summary line that adds to the total (for example Subtotal and Driver tip), each as `{"name": ..., "amount": ...}`, named and valued as Amazon shows it, including lines showing `0.00`.
- `discounts`: every summary line that reduces the total, in the same form. `[]` if none.
- Leave the Order Total line itself out of `charges` and `discounts`. Amazon's lines in `charges` minus `discounts` must reproduce `order_total`; if they do not, report it and copy what Amazon shows anyway.

**Digital Order** (nothing to ship)
- `charge_date`: the date Amazon charged it.
- `short_name`: what was bought, in plain words (for example `Grocery Subscription`), by the same rules as an Item's `short_name`.
- `order_total`: the amount shown.
- `payment`: the card taken from the Order's details page.
- Leave Prime membership fees and Audible out. Steven enters those by hand.

**Refund** (in `refunds`, one entry per refund Amazon shows)
- `order_number` and `positions`: the Order and the Items the refund is for. One refund Amazon shows against several Items is one entry listing all their positions. Never split its amount.
- A refund on a Whole Foods Order has no Items: `positions: []`.
- `amount`: the refund amount Amazon shows, positive.
- `refund_date`: the date shown for the refund (issued or processed). When only "expected by" is shown and the money has not come back, skip it and tell Steven.
- Partial refunds on one Item are separate entries.
