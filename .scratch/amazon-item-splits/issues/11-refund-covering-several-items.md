# 11: Refund covering several Items

**What to build:** One Refund that Amazon shows against several Items becomes one negative row per Item, so each part follows its own Item's classification. See spec addendum decision 6.

**Blocked by:** 08

**Status:** resolved

- [x] A Refund carries `positions` (a list). One position behaves exactly as `position` did.
- [x] Several positions: the amount is split in proportion to the Items' Loaded Costs, leftover cent to the largest part. Each row has its own key (`... #<position> refund <date> <part>`) and copies its own Item's "Send to Splitwise" and "For who".
- [x] A position that matches no shipped Item, or an Item before the cutoff, skips the whole Refund with the existing warnings.
- [x] Adapter-seam tests: the split and its keys. CLI-seam test: one Personal and one Shared Item under one Refund get different classifications, and a re-scrape writes nothing.

## Comments

- 2026-10-01 Open question: must the old single `position` on a Refund still be accepted? Went with: no, `positions` is required and a Refund with only `position` fails with an error naming the Order and `positions`. Why: the spec addendum says `positions` replaces `position` in schema version 2, and a silent fallback would hide a prompt that disagrees with the importer. Fixtures, tests and `scrape-amazon-orders.md` now use `positions`.
- 2026-10-01 Open question: what is `<part>` in the per-Item key? Went with: that Item's part amount, e.g. `#2 refund 2026-08-20 5.00`. A one-position Refund keeps the full amount, so its key is unchanged. Why: the existing key format already ends in the row's amount, and a part amount keeps parts on different Items distinct.
- 2026-10-01 Open question: how to split when the parts need rounding? Went with: the existing `_spread` helper (round down, leftover cents to the parts that lost most, ties to the larger Loaded Cost, then the earlier position). Why: it never yields a negative part and always sums exactly; the ticket's "leftover cent to the largest part" is the same rule for the tie case, and giving it all to the largest part is the bug the last `fix:` commit removed.
- 2026-10-01 Open question: a part that rounds to 0.00 (e.g. $0.01 across two Items)? Went with: no row for that part. Why: a zero row is noise in the sheet and Splitwise; the remaining parts still sum to the Refund.
- 2026-10-01 Open question: `positions: []` on a physical Order, or repeated positions? Went with: an error naming the Order. Why: the addendum allows `[]` only for a Whole Foods Order (ticket 12), and a repeated position would double-weight one Item.
- 2026-10-01 Open question: which Item's date is named when several are before the cutoff? Went with: the first one listed, one warning and one skip count for the whole Refund. Why: the Refund is skipped as a unit, so one warning is enough to tell Steven to enter it by hand.
