# 11: Refund covering several Items

**What to build:** One Refund that Amazon shows against several Items becomes one negative row per Item, so each part follows its own Item's classification. See spec addendum decision 6.

**Blocked by:** 08

**Status:** ready-for-agent

- [ ] A Refund carries `positions` (a list). One position behaves exactly as `position` did.
- [ ] Several positions: the amount is split in proportion to the Items' Loaded Costs, leftover cent to the largest part. Each row has its own key (`... #<position> refund <date> <part>`) and copies its own Item's "Send to Splitwise" and "For who".
- [ ] A position that matches no shipped Item, or an Item before the cutoff, skips the whole Refund with the existing warnings.
- [ ] Adapter-seam tests: the split and its keys. CLI-seam test: one Personal and one Shared Item under one Refund get different classifications, and a re-scrape writes nothing.
