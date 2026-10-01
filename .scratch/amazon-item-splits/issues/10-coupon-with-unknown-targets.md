# 10: Coupon with unknown targets

**What to build:** When Amazon shows a coupon total but not which Items it applied to, the Order still imports. The coupon is treated as an Adjustment across all Items. See spec addendum decision 4.

**Blocked by:** 08

**Status:** resolved

- [x] A Promo with `positions: []` is spread across all non-cancelled Items in proportion to price after their own Promos, and appears in the formula's discount term.
- [x] A warning names the Order and the amount.
- [x] A Promo whose listed positions are all cancelled Items is still ignored, as today.
- [x] Adapter-seam tests: a two-Item Order with an untargeted coupon passes the total check, and the warning is present.

## Comments

- 2026-10-01 Open question: when is the untargeted-coupon warning emitted? Went with: only when the Order is imported (not for an Order skipped by the cutoff or the total check). Why: a skipped Order already gets its own warning, and an old Order's coupon is not Steven's concern.
- 2026-10-01 Open question: how does the coupon combine with whole-Order discounts? Went with: each is spread separately by price after Promos, and both land in the one discount term of the formula. Why: matches CONTEXT.md (Adjustment) and keeps the formula's fixed term order.
- 2026-10-01 Open question: warning for an untargeted coupon on an Order with no live Items? Went with: none, the Promo is ignored. Why: there is nothing to spread it over.
