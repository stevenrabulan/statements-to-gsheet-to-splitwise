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
One line on an Order (a product, possibly with quantity greater than 1). For Amazon, an Item is the unit that gets one sheet row.
_Avoid_: Product, line, SKU

**Ready Order**:
An Amazon Order whose non-cancelled Items have all shipped. Only a Ready Order is imported; the rest are held for a later scrape.
_Avoid_: Complete order, finished order

**Cutoff Date**:
The first day of spending tracked for an Account or for Amazon Orders; anything earlier was recorded some other way and is ignored. For Amazon it is compared with an Item's shipment ship date, not the Order Date.
_Avoid_: Start date, ignore date

### Cost

**Loaded Cost**:
An Item's true cost: its price, minus the Promos that target it, plus its tax, plus its share of Adjustments. The Loaded Costs of an Order's Items sum to the Order total. It does not depend on how the Order was paid (gift card and points are payment, not discounts). _(Payment independence assumed by default.)_
_Avoid_: Item total, effective cost

**Promo**:
A discount Amazon shows against specific Items. It reduces only the Items it targets.
_Avoid_: Coupon, savings

**Adjustment**:
An Order-level amount not tied to one Item: shipping, or a discount on the whole Order. It is spread across Items in proportion to their price after their own Promos. _(Order-wide discounts as Adjustments assumed by default.)_
_Avoid_: Fee, extra, order-level promo

**Refund**:
Money Amazon returns against a specific Item (a return or a partial refund). It carries the same Share Type as the Item it refunds. _(Assumed by default.)_
_Avoid_: Return credit, reversal

### Classification

**Share Type**:
Who pays for an Item: **Personal** (the buyer only), **Shared** (split 50/50), or **Partner's** (Partner pays in full). _(Assumed: accepted by default in the grilling session, not stated explicitly.)_
_Avoid_: Split type, category
