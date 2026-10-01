# 10: Coupon with unknown targets

**What to build:** When Amazon shows a coupon total but not which Items it applied to, the Order still imports. The coupon is treated as an Adjustment across all Items. See spec addendum decision 4.

**Blocked by:** 08

**Status:** ready-for-agent

- [ ] A Promo with `positions: []` is spread across all non-cancelled Items in proportion to price after their own Promos, and appears in the formula's discount term.
- [ ] A warning names the Order and the amount.
- [ ] A Promo whose listed positions are all cancelled Items is still ignored, as today.
- [ ] Adapter-seam tests: a two-Item Order with an untargeted coupon passes the total check, and the warning is present.
