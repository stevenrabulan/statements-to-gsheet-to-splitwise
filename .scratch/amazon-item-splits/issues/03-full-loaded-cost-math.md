# 03: Full Loaded Cost math

**What to build:** Multi-Item Orders get correct Loaded Costs, so when Steven shares only some Items in an Order, each Item row already carries its exact price, Promos, tax, and share of shipping. An Order whose calculated costs don't match Amazon's Order total is skipped rather than imported wrong (ADR 0002). See the spec's "Loaded Cost calculation" and "Amount formula" sections.

**Blocked by:** 02 (Tracer bullet: one simple Amazon Order becomes one Item row)

**Status:** ready-for-agent

- [ ] A Promo reduces only the Items it targets. A Promo targeting several Items is spread across them in proportion to line price.
- [ ] Per-Item tax is used when present. Otherwise the shipment's tax is spread across its non-cancelled Items in proportion to net price (price after Promos), and a single-Item shipment takes its tax exactly.
- [ ] Shipping and whole-Order discounts are each spread across Items in proportion to net price, at the smallest scope Amazon shows (shipment or Order).
- [ ] Each spread component's parts sum exactly to its source. The leftover cent goes to the largest part.
- [ ] The Amount formula terms appear in fixed order: quantity × unit price, minus the Promo share, plus tax, plus the shipping share, then the whole-Order discount share as a subtraction. Zero terms are omitted, and the formula's value equals the Loaded Cost.
- [ ] If an Order's Loaded Costs don't sum to the Order total Amazon showed, the whole Order is skipped with a warning naming the Order, the expected total, and the calculated total.
- [ ] How the Order was paid (gift card, points) never changes Loaded Cost.
- [ ] Adapter tests cover:
  - [ ] a multi-Item shipment with shipment tax
  - [ ] a Promo on one Item, and a Promo on several Items
  - [ ] shipping and a whole-Order discount
  - [ ] a rounding remainder
  - [ ] a total mismatch
