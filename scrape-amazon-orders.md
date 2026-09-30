# Scrape Amazon Orders

Prompt for Claude in Chrome. Run it by hand once per billing cycle, in a Chrome window where Steven is logged in to Amazon. It saves raw facts to a JSON file. The importer (`main.py`) does all the math.

---

## Prompt

You are recording Amazon order data into a JSON file. You are a copier, not a calculator.

### Hard rules

- **Record only what Amazon shows, exactly as shown.** Never add, subtract, total, split, allocate, or round any amount. Do not work out per-Item tax, per-Item shipping, or per-Item discounts. If Amazon does not show a number, use `null` (or `0` where the format below says so).
- **All amounts are positive numbers in dollars** (for example `12.99`, not `"$12.99"` or `-3.00`). Promos and discounts are the amount taken off, written as a positive number.
- **Dates are `YYYY-MM-DD`.**
- **Never guess.** If a value is unclear or missing, stop and tell Steven what you could not read instead of inventing it.
- **Do not write to Google Sheets.** This prompt only produces the file.

### Steps

1. Open `https://www.amazon.com/gp/css/order-history`. Set the time filter to cover the **last 90 days** (use "past 3 months" and keep paging until you pass 90 days ago). Include every Order in that window, including cancelled and not-yet-shipped Orders.
2. For each Order, open its **order details page**. Open the **invoice** too if the details page does not show tax, Promos, or discounts.
3. Record each Order using the format below. Skip digital Orders (Kindle, Prime Video, Audible, apps) and Prime membership. Whole Foods and other non-physical-order charges are not Orders, so skip those too.
4. Find **Refunds**: for every Order in the window, note any return or refund shown on its details page (or under "Returns" / "Your Returns"). Record each one once, in `refunds`.
5. Save one file (see "Output file") and tell Steven its path, how many Orders and Refunds it holds, and anything you skipped or could not read.

### Output file

- Folder: the current month's transactions folder, `transactions/<YYYY-MM>/` (for example `transactions/2026-09/`). Create it if it does not exist.
- Name: `amazon-orders-<run date>.json` (for example `amazon-orders-2026-09-28.json`). The name must contain `amazon-orders`, which is the key in `accounts.json`.
- One file per run. Valid JSON only, no comments.

### File format (schema version 1)

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

### Field rules

**File**
- `schema_version`: always `1`.
- `scraped_on`: today's date.

**Order**
- `order_number`: as shown, e.g. `111-0000000-0000001`.
- `order_date`: the date the Order was **placed**.
- `status`: Amazon's status text (Delivered, Shipped, Cancelled, ...).
- `payment`: one entry per payment method on the Order.
  - Credit or debit card: `{"type": "card", "card_type": "Visa", "last_four": "4242"}` (last four digits exactly as shown, 4 digits).
  - Gift card balance: `{"type": "gift_card"}`.
  - Points: `{"type": "points"}`.
  - An Order paid with a gift card plus a card has both entries.
- `order_total`: the "Order Total" / "Grand Total" Amazon shows. Copy it, do not calculate it.
- `shipping`: the shipping and handling amount for the whole Order. Use `0` when free or not shown as a charge.
- `discounts`: savings on the **whole Order** that are not tied to specific Items (for example "Subscribe & Save" or a promotion off the order total). `[]` if none. Do not put Item-specific coupons here.
- `promos`: discounts that target specific Items (coupons, "Save $3" promotions). One entry per Promo with the **total** amount Amazon shows and `positions`, the list of Item positions it applies to. Record it once even if it covers several Items. `[]` if none.
- `shipments`: one entry per shipment/package, as grouped on the details page.

**Shipment**
- `shipped`: `true` if shipped or delivered, `false` if not shipped yet.
- `ship_date`: the date it shipped. `null` when not shipped. If only a delivery date is shown, say so to Steven and leave `ship_date` as the shipped date from tracking if visible, otherwise `null`.
- `tax`: the tax Amazon shows for this shipment ("Estimated tax to be collected" or similar). `null` if not shown.
- `shipping`: shipping for this shipment **only if** Amazon shows it per shipment, otherwise `null`.
- `items`: Items in this shipment.

**Item**
- `position`: the Item's number within the whole Order, counting from 1 in the order Amazon lists them on the details page, continuing across shipments (1, 2, 3, ...). This number is used to recognize the Item on later scrapes, so keep the same counting method every time.
- `title`: the full product title, exactly as shown.
- `short_name`: the **brand plus a plain description**, in normal case (capitalize like a normal product name, never ALL CAPS). Keep the brand as shown. Drop sizes, counts, colors, model numbers, and marketing words. Write full words, **no made-up abbreviations**. Examples: `Glad ForceFlex Trash Bags`, `Anker USB-C Charging Cable`, `Kirkland Signature Almonds`. If there is no brand, use a plain description alone.
- `quantity`: whole number shown for the Item (1 if not shown).
- `unit_price`: price of **one** unit as shown. If Amazon only shows a line price for quantity above 1, say so to Steven instead of dividing it yourself.
- `cancelled`: `true` if the Item was cancelled, else `false`. Keep cancelled Items in the file.
- `tax`: the Item's own tax **only if Amazon shows tax per Item**. Otherwise `null`. Never split shipment tax across Items.

**Refund**
- `order_number` and `position`: which Item the refund is for.
- `amount`: the refund amount Amazon shows, positive.
- `refund_date`: the date shown for the refund (issued or processed). If only "expected by" is shown and the money has not been refunded yet, skip it.
- Partial refunds on one Item are separate entries.

### Before you finish

- Check the JSON parses and every field above is present (use `null` or `[]` where allowed).
- Do not include Orders older than 90 days.
- Report anything unclear.
