# 03: Full Loaded Cost math

**What to build:** Multi-Item Orders get correct Loaded Costs, so when Steven shares only some Items in an Order, each Item row already carries its exact price, Promos, tax, and share of shipping. An Order whose calculated costs don't match Amazon's Order total is skipped rather than imported wrong (ADR 0002). See the spec's "Loaded Cost calculation" and "Amount formula" sections.

**Blocked by:** 02 (Tracer bullet: one simple Amazon Order becomes one Item row)

**Status:** done

- [x] A Promo reduces only the Items it targets. A Promo targeting several Items is spread across them in proportion to line price.
- [x] Per-Item tax is used when present. Otherwise the shipment's tax is spread across its non-cancelled Items in proportion to net price (price after Promos), and a single-Item shipment takes its tax exactly.
- [x] Shipping and whole-Order discounts are each spread across Items in proportion to net price, at the smallest scope Amazon shows (shipment or Order).
- [x] Each spread component's parts sum exactly to its source. The leftover cent goes to the largest part.
- [x] The Amount formula terms appear in fixed order: quantity × unit price, minus the Promo share, plus tax, plus the shipping share, then the whole-Order discount share as a subtraction. Zero terms are omitted, and the formula's value equals the Loaded Cost.
- [x] If an Order's Loaded Costs don't sum to the Order total Amazon showed, the whole Order is skipped with a warning naming the Order, the expected total, and the calculated total.
- [x] How the Order was paid (gift card, points) never changes Loaded Cost.
- [x] Adapter tests cover:
  - [x] a multi-Item shipment with shipment tax
  - [x] a Promo on one Item, and a Promo on several Items
  - [x] shipping and a whole-Order discount
  - [x] a rounding remainder
  - [x] a total mismatch

## Comments

**Implemented (2026-09-29).** Notes for later tickets:

- The "needs cost allocation" guard is gone. Cancelled Items are now excluded from the math and from the rows (ticket 04 still owns readiness and the cutoff).
- Shipment tax includes any per-Item tax Amazon also shows: own-tax Items keep theirs, and the remainder is spread across the shipment's other Items.
- Shipping: a shipment's own `shipping` spreads over that shipment's Items, and Order `shipping` spreads over all Items. Both add up if both are shown.
- Skipped reason for a failed total check is "total mismatch".
