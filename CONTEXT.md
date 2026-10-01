# Split Transactions

Turns spending from bank, card, and Amazon order data into rows on the "Split payments" sheet, which feeds Splitwise.

## Language

### Money sources

**Account**:
A source of transactions, either a card or a bank account. Its label is the sheet's Payment Method column.
_Avoid_: Card name, source

**Charge**:
One posted line on an Account's statement or export. Amazon posts one Charge per shipment, so a Charge does not correspond to an Order.
_Avoid_: Transaction (when talking about the statement line specifically)

**Order**:
One Amazon purchase, identified by its Amazon order number. It contains one or more Items.
_Avoid_: Purchase, Amazon transaction

**Item**:
One line on an Order (a product, possibly with quantity greater than 1). For Amazon, an Item is the unit that gets one sheet row, except in a Whole Foods Order.
_Avoid_: Product, line, SKU

**ASIN**:
Amazon's 10-character code for what an Item is, taken from the Item's link on the Order. It identifies the Item's sheet row across scrapes, because Amazon lists an Order's Items in a different order from one page load to the next.
_Avoid_: SKU, position (as the Item's identity)

**Whole Foods Order**:
An Order placed with Whole Foods through Amazon. It gets one sheet row for the whole Order, not one per Item.
_Avoid_: Grocery order, WFM order

**Digital Order**:
An Amazon Order with nothing to ship: a subscription charge, e-book, video, or app. It gets one sheet row, dated when it was charged.
_Avoid_: Digital purchase, subscription charge

**Ready Order**:
An Amazon Order whose non-cancelled Items have all shipped. Only a Ready Order is imported; the rest are held for a later scrape.
_Avoid_: Complete order, finished order

**Cutoff Date**:
The first day of spending tracked for an Account or for Amazon Orders; anything earlier was recorded some other way and is ignored. For Amazon it is compared with an Item's shipment ship date, not the Order Date; when Amazon doesn't show a ship date, the Order Date stands in for it.
_Avoid_: Start date, ignore date

### Cost

**Loaded Cost**:
An Item's true cost: its price, minus the Promos that target it, plus its tax, plus its share of Adjustments. The Loaded Costs of an Order's Items sum to the Order Total. It does not depend on how the Order was paid (gift card and points are payment, not discounts). _(Payment independence assumed by default.)_
_Avoid_: Item total, effective cost

**Order Total**:
What an Order cost before any gift card or points were applied. On Amazon's summary it is the total above the gift card line, not the "Grand Total" after it. _(Assumed by default.)_
_Avoid_: Grand total, amount charged

**Promo**:
A discount Amazon shows against specific Items. It reduces only the Items it targets. A discount whose targets Amazon doesn't show is an Adjustment, not a Promo. _(Assumed by default.)_
_Avoid_: Coupon, savings

**Adjustment**:
An Order-level amount not tied to one Item: shipping, or a discount on the whole Order. It is spread across Items in proportion to their price after their own Promos. _(Order-wide discounts as Adjustments assumed by default.)_
_Avoid_: Fee, extra, order-level promo

**Refund**:
Money Amazon returns against a specific Item (a return or a partial refund). It carries the same Share Type as the Item it refunds. _(Assumed by default.)_ A Refund on a Whole Foods Order is against the whole Order, since it has no Item rows. One Refund can cover several Items; it is split between them in proportion to their Loaded Cost. _(Assumed by default.)_
_Avoid_: Return credit, reversal

### Classification

**Share Type**:
Who pays for an Item: **Personal** (the buyer only), **Shared** (split 50/50), or **Partner's** (Partner pays in full). _(Assumed: accepted by default in the grilling session, not stated explicitly.)_
_Avoid_: Split type, category
